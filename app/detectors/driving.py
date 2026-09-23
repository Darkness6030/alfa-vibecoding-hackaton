"""Russian driving licence format with RU/EN labels."""

from app.detectors.base import context_before
from app.detectors.passport import DocumentNumberDetector, driving_context


class DrivingLicenseDetector(DocumentNumberDetector):
    type = "DRIVING_LICENSE"
    priority = 50

    def validate(self, text, match):
        return driving_context(context_before(text, match, 6))
