# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from chz import get_chz_stock, print_stock_report

# Get stock for ALL groups without date filter
stock = get_chz_stock()  # defaults to beer+nabeer+softdrinks, no date filter
print_stock_report(stock)
