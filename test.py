
import logging
from tplink_smartplug import discoveryTest, SmartPlug

def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(message)s')

    discoveryTest()
    
    
if __name__ == "__main__":
    main()