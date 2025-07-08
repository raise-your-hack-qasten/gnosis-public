from threading import Thread
from openrecall.screenshot import record_screenshots_thread


if __name__ == "__main__":

    # Start the thread to record screenshots
    t = Thread(target=record_screenshots_thread)
    t.start()
