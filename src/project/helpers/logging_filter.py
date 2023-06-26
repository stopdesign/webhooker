from logging import Filter

class SkipStaticFilter(Filter):
    """Logging filter to skip logging of staticfiles to terminal"""

    def filter(self, record):
        return '"GET /static/' not in record.getMessage()
