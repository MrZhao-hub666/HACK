"""Publish the current foreign catalogue workbook."""
from app.foreign_sync import synchronize

if __name__ == "__main__":
    print(synchronize())
