from os.path import join, dirname, abspath, pardir
from time import strftime
from netifaces import interfaces


# defaults for batch and instance numbers
NUM_BATCHES = 10
NUM_INSTANCES = 4
MAX_SITES_PER_TOR_PROCESS = 100  # reset tor process after crawling 100 sites

# max capture size in KB
MAX_DUMP_SIZE = 40000
# max filename length
MAX_FNAME_LENGTH = 200
STREAM_CLOSE_TIMEOUT = 20  # wait 20 seconds before raising an alarm signal
# otherwise we had many cases where get_streams hanged

# timeouts
SOFT_VISIT_TIMEOUT = 70     # timeout used by selenium and sniffer
# signal based hard timeout in case soft timeout fails
HARD_VISIT_TIMEOUT = SOFT_VISIT_TIMEOUT + 10

DEFAULT_SOCKS_PORT = 9051

CRAWLER_TYPES = ['Base', 'WebFP', 'Multitab', 'Middle']

# retries
MAX_RETRIES = 1

# virtual display dimensions
DEFAULT_XVFB_WIN_W = 1280
DEFAULT_XVFB_WIN_H = 800
# virt_display is a string in the form of WxH
# W = width of the virtual display
# H = height of the virtual display
# e.g. "1280x800" or "800x600"
DEFAULT_XVFB_WINDOW_SIZE = "%sx%s" % (DEFAULT_XVFB_WIN_W, DEFAULT_XVFB_WIN_H)

# Default paths
BASE_DIR = abspath(join(dirname(__file__), pardir))
CONFIG_FILE = join(BASE_DIR, 'config.ini')
RESULTS_DIR = join(BASE_DIR, 'results')
ETC_DIR = join(BASE_DIR, 'etc')
CONFIG_DIR = join(BASE_DIR, 'config')
DEFAULT_CONFIG_DIR = join(CONFIG_DIR, "default")
TORRC_FILE = join(DEFAULT_CONFIG_DIR, 'torrc')
FFPREF_FILE = join(DEFAULT_CONFIG_DIR, 'ffprefs')
SRC_DIR = join(BASE_DIR, 'tbcrawler')


def set_crawl_id(crawl_id=None):
    global CRAWL_ID, CRAWL_DIR, LOGS_DIR, CRAWL_LOG_FILENAME, TOR_LOG_FILENAME
    if crawl_id is None:
        CRAWL_ID = strftime('%y%m%d_%H%M%S')
    else:
        CRAWL_ID = crawl_id
    CRAWL_DIR = join(RESULTS_DIR, CRAWL_ID)
    LOGS_DIR = join(CRAWL_DIR, 'logs')
    CRAWL_LOG_FILENAME = join(LOGS_DIR, 'crawl.log')
    TOR_LOG_FILENAME = join(LOGS_DIR, 'tor.log')

set_crawl_id()

ONIONPERF_DIR = join(BASE_DIR, 'onionperf', 'onionperf')
PCAP_FILENAME = 'capture.pcap'
TSHARK_FILENAME = 'capture.tshark'
SCREENSHOT_FILENAME = "screenshot.png"
FF_LOG_FILENAME = 'ff.log'
ONIONPERF_FNAME = 'onionperf.log'

TEST_DIR = join(SRC_DIR, 'test')
TEST_FILES_DIR = join(TEST_DIR, 'files')
TBB_DIR = join(BASE_DIR, 'tor-browser_en-US')
# Top URLs localized (DE) to prevent the effect of localization
LOCALIZED_DATASET = join(ETC_DIR, "localized-urls-100-top.csv")
DEFAULT_ADDONS_DIR = join(BASE_DIR, "addons")

IFACES = interfaces()
VBOX_GATEWAY_IP = "10.0.2.2"  # default gateway IP of VirtualBox
LXC_GATEWAY_IP = "10.0.3.1"  # default gateway IP of LXC
LOCALHOST_IP = "127.0.0.1"  # default localhost IP
LOCAL_IP = LOCALHOST_IP
DEFAULT_FILTER = 'tcp and not host %s and not tcp port 22 and not tcp port 20' % LOCALHOST_IP

class TimeoutException(Exception):
    pass

class ConnErrorPage(Exception):
    pass


class HardTimeoutException(Exception):
    pass
