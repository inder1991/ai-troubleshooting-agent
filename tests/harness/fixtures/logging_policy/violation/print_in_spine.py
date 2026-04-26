"""Fixture: print() in spine should fire Q16.no-print-in-spine."""


def handle_request(payload):
    print("processing", payload)
    return payload
