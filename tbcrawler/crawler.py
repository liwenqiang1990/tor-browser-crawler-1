from os import remove
from tempfile import gettempdir
from os.path import join, isfile
from pprint import pformat
from urlparse import urlsplit
from time import sleep
from shutil import move, rmtree
import pickle
import stem
#from pykeyboard import PyKeyboard

from selenium.common.exceptions import TimeoutException, WebDriverException
from tbselenium.tbdriver import TorBrowserDriver
from tbselenium.exceptions import TBDriverPortError
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains

import common as cm
import utils as ut
from dumputils import TShark, SnifferTimeoutError
from onionperf_port import Onionperf
from log import wl_log

HTTP_DUMP_ADDON_LOG = 'tbb-http.log'  # log file generated by the addon
CHECK_CAPTCHA = False  # disable captcha check as it is confused with the indexing
RETRY = False
MAX_FAILED = 3
MAX_BATCH_FAILED = 4


class CrawlerBase(object):
    def __init__(self, controller, driver_config, device='eth0', screenshots=True):
        self.controller = controller
        self.driver_config = driver_config
        self.screenshots = screenshots
        self.device = device
        self.job = None

    def crawl(self, job):
        """Crawls a set of urls in batches."""
        self.job = job
        wl_log.info("Starting new crawl")
        wl_log.info(pformat(self.job))
        with self.controller.launch():
            while self.job.batch < self.job.batches:
                wl_log.info("**** Starting batch %s ***" % self.job.batch)
                self._do_batch()
                sleep(float(self.job.config['pause_between_batches']))
                self.job.batch += 1

    def post_visit(self):
        pass

    def cleanup_visit(self):
        pass

    def _do_batch(self):
        """
        Must init/restart the Tor process to have a different circuit.
        If the controller is configured to not pollute the profile, each
        restart forces to switch the entry guard.
        """
        while self.job.site < len(self.job.urls):
            if self.job.url in self.job.batch_failed and self.job.batch_failed[self.job.url]:
                wl_log.info("Skipping URL because has failed too many times")
                self.job.site += 1
                continue

            if len(self.job.url) > cm.MAX_FNAME_LENGTH:
                wl_log.warning("URL is too long: %s" % self.job.url)
                self.job.site += 1
                continue

            self._do_visits()
            sleep(float(self.job.config['pause_between_sites']))
            self.job.site += 1
        if self.job.site == len(self.job.urls):
            self.job.site = 0

    def _new_identity(self):
        wl_log.info("Creating a new identity...")
        try:
            ActionChains(self.driver).send_keys(Keys.CONTROL + Keys.SHIFT + 'U').perform()
        except WebDriverException:
            pass
        except Exception:
            wl_log.exception("Exception while creating new identity.")

    def _reset_tor(self):
        if 'restart_tor_for_every_visit' in self.job.config and\
                self.job.config['restart_tor_for_every_visit']:
            self._new_identity()
            self.controller.controller.drop_guards()

    def _mark_failed(self):
        url = self.job.url
        if url in self.job.batch_failed and not self.job.batch_failed[url]:
            self.job.batch_failed[url] = True
            wl_log.info("Visit to %s in %s different batches: won't visit the url again" % (url, MAX_BATCH_FAILED))
        else:
            self.job.batch_failed[url] = False
            wl_log.info("Visit to %s failed %s times within this batch, will skip for this batch" % (url, MAX_FAILED))

    def _config_driver(self):
        # set specific log for this visit
        self.driver_config['tbb_logfile_path'] = self.job.log_file_batch

    def _do_visits(self):
            self._config_driver()
            with TorBrowserDriver(**self.driver_config) as driver:
                self.driver = driver
                failed = 0
                while self.job.visit < self.job.visits:
                    self.job.visit += 1

                    raised = False
                    num_retry, retry = 0, RETRY
                    while True:
                        wl_log.info("*** Visit #%s to %s ***", self.job.visit, self.job.url)
                        try:
                            ut.create_dir(self.job.path)
                            self.save_checkpoint()
                            self.set_page_load_timeout()
                            try:
                                self._do_instance()
                                self.get_screenshot_if_enabled()
                            except (cm.HardTimeoutException, TimeoutException, SnifferTimeoutError):
                                wl_log.exception("Visit to %s has timed out!", self.job.url)
                            else:
                                self.post_visit()
                            finally:
                                self._reset_tor()
                                self.cleanup_visit()
                        except OSError as ose:
                            wl_log.exception("OS Error %s" % repr(ose))
                            raise ose  # we better halt here, we may be out of disk space
                        except TBDriverPortError as tbde:
                            raise tbde # cannot connect to Tor, the following ones will fail
                        except cm.ConnErrorPage as cnpe:
                            raised = cnpe
                        except stem.SocketError as sckte:
                            raised = sckte
                        except Exception as exc:
                            wl_log.exception("Unknown exception: %s" % repr(exc))
                            raised = exc
                        finally:
                            if not raised:
                                break

                            # there was a non-timeout exception
                            failed += 1
                            if failed >= MAX_FAILED:
                                self._mark_failed()
                                self.job.visit = self.job.visits
                                break

                            # retry visit?
                            if not retry:
                                break
                            wl_log.info("Will retry the visit. Retry num %s/%s" % (retry, cm.MAX_RETRIES))
                            rmtree(self.job.path)
                            num_retry += 1
                            if num_retry == cm.MAX_RETRIES:
                                retry = False
                            self.controller.restart_tor()


                if self.job.visit == self.job.visits:
                    self.job.visit = 0

    def _get_url(self):
        return self.job.url

    def _do_instance(self):
        with Onionperf(self.job.onionperf_log):
            with TShark(device=self.device,
                        path=self.job.pcap_file, filter=cm.DEFAULT_FILTER):
                sleep(1)  # make sure sniffer is running
                with ut.timeout(cm.HARD_VISIT_TIMEOUT):
                    wl_log.info("Visiting: %s" % self.job.url)
                    self.driver.get(self._get_url())
                    self.page_source = self.driver.page_source.encode('utf-8').strip().lower()
                    self.save_page_source()
                    self.check_conn_error()
                    self.check_captcha()
                    sleep(float(self.job.config['pause_in_site']))  # TODO

    def save_page_source(self):
        with open(join(self.job.path, "source.html"), "w") as fhtml:
            fhtml.write(self.page_source)

    def check_conn_error(self):
        if self.driver.current_url == "about:newtab":
            wl_log.warning('Stuck in about:newtab, visit #%s to %s'
                           % (self.job.visit, self.job.url))
        if self.driver.is_connection_error_page:
            wl_log.warning('Connection Error, visit  #%s to %s'
                           % (self.job.visit, self.job.url))
            raise cm.ConnErrorPage

    def check_captcha(self):
        if CHECK_CAPTCHA and ut.has_captcha(self.page_source):
            wl_log.warning('captcha found')
            self.job.add_captcha()

    def save_checkpoint(self):
        fname = join(cm.CRAWL_DIR, "job.chkpt")
        if isfile(fname):
            remove(fname)
        with open(fname, "w") as f:
            pickle.dump(self.job, f)
        wl_log.info("New checkpoint at %s" % fname)

    def set_page_load_timeout(self):
        try:
            self.driver.set_page_load_timeout(
                cm.SOFT_VISIT_TIMEOUT)
        except WebDriverException as seto_exc:
            wl_log.error("Setting soft timeout %s", seto_exc)

    def get_screenshot_if_enabled(self):
        if self.screenshots:
            try:
                with ut.timeout(5):
                    self.driver.get_screenshot_as_file(self.job.png_file)
            except Exception:
                wl_log.error("Cannot get screenshot.")


class CrawlerWebFP(CrawlerBase):

    def _get_url(self):
        return self.job.url + '#%s' % self.job.uid

    def cleanup_visit(self):
        # attempt to move files to job's dir
        self.move_logs()
        addon_logfile = join(gettempdir(), HTTP_DUMP_ADDON_LOG)
        if isfile(addon_logfile):
            remove(addon_logfile)

    def post_visit(self):
        sleep(float(self.job.config['pause_between_visits']))

    def move_logs(self):
        if isfile(self.job.tshark_file):
            self.filter_packets_without_guard_ip()
        # move addon log to job's directory
        addon_logfile = join(gettempdir(), HTTP_DUMP_ADDON_LOG)
        if isfile(addon_logfile):
            move(addon_logfile, join(self.job.path, HTTP_DUMP_ADDON_LOG))

    def filter_packets_without_guard_ip(self):
        guard_ips = set([ip for ip in self.controller.get_all_guard_ips()])
        wl_log.info("Found %s guards in the consensus.", len(guard_ips))
        wl_log.info("Filtering packets without a guard IP.")
        try:
            ut.filter_tshark(self.job.tshark_file, guard_ips)
        except Exception as e:
            wl_log.error("ERROR: filtering tshark log: %s.", e)
            wl_log.error("Check tshark log: %s", self.job.thsark_file)


class CrawlerMultitab(CrawlerWebFP):
    pass


class CrawlJob(object):
    def __init__(self, config, urls):
        self.urls = urls
        self.visits = int(config['visits'])
        self.batches = int(config['batches'])
        self.config = config
        self.batch_failed = {}

        # state
        self.site = 0
        self.visit = 0
        self.batch = 0
        self.captchas = [False] * (self.batches * len(self.urls) * self.visits)

    def add_captcha(self):
        try:
            captcha_filepath = ut.capture_dirpath_to_captcha(self.path)
            move(self.path, captcha_filepath)

            self.captchas[self.global_visit] = True
        except OSError as e:
            wl_log.exception('%s could not be renamed to %s',
                             self.path, captcha_filepath)
            raise e

    @property
    def pcap_file(self):
        return join(self.path, cm.PCAP_FILENAME)

    @property
    def tshark_file(self):
        return join(self.path, cm.TSHARK_FILENAME)

    @property
    def onionperf_log(self):
        return join(self.path, cm.ONIONPERF_FNAME)

    @property
    def log_file(self):
        return join(self.path, cm.FF_LOG_FILENAME)

    @property
    def log_file_batch(self):
        return join(cm.LOGS_DIR, "%s.%s.%s" % (cm.FF_LOG_FILENAME, self.visit, self.batch))

    @property
    def png_file(self):
        return join(self.path, cm.SCREENSHOT_FILENAME)

    @property
    def instance(self):
        return self.batch * self.visits + self.visit

    @property
    def global_visit(self):
        global_visit_no = self.site * self.visits + self.instance
        return global_visit_no

    @property
    def uid(self):
        return '-'.join(map(str, [cm.CRAWL_ID, self.url[7:-6],
                                  self.batch, self.site, self.visit]))

    @property
    def url(self):
        return self.urls[self.site]

    @property
    def path(self):
        website = urlsplit(self.url).hostname
        attributes = [self.batch, website, self.instance]
        if self.global_visit in self.captchas and self.captchas[self.global_visit]:
            attributes.insert(0, 'captcha')

        return join(cm.CRAWL_DIR, "_".join(map(str, attributes)))

    def __repr__(self):
        return "Batches: %s/%s, Sites: %s/%s, Visits: %s/%s" \
            % (self.batch + 1, self.batches,
               self.site + 1, len(self.urls),
               self.visit + 1, self.visits)