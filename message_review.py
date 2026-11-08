"""Explain common message warning signs without visiting links or executing instructions."""
import re


SAMPLES = [
    {"id": "delivery", "title": "Example delivery scam", "text": "URGENT: Your parcel is on hold. Pay a small redelivery fee now at https://delivery-example.invalid/verify or your package will be returned."},
    {"id": "code", "title": "Example verification-code request", "text": "This is account support. Tell me your one-time verification code immediately so we can stop your account from being suspended."},
    {"id": "ordinary", "title": "Example ordinary reminder", "text": "Hi! Our project meeting is at 3 PM in the library. Please bring your notes. See you there."},
]


def review_message(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("Enter a message between 1 and 4,000 characters")
    rules = [
        (r"\b(urgent|immediately|act now|right now|suspend\w*|within \d+|will be returned)\b", "Pressure or threatened consequences", "Pressure can discourage you from checking the request independently."),
        (r"\b(password|verification code|one[- ]time (?:password|code)|otp|social security|ssn)\b", "Sensitive information or verification codes", "A request to share credentials or codes deserves independent verification."),
        (r"\b(pay|payment|fee|gift cards?|wire transfer|crypto\w*|bank details)\b", "Money or payment request", "Confirm payment requests through a channel you already trust."),
        (r"https?://|www\.", "External link", "A link alone does not prove fraud. Verify the destination through the organization's official app or a known address."),
    ]
    signals = [{"title": title, "detail": detail} for pattern, title, detail in rules if re.search(pattern, text, re.I)]
    return {
        "method": "Rule-based review · AI is not used for this result",
        "verdict": "Review before acting" if signals else "No common warning signs detected",
        "signals": signals,
        "summary": "This message contains patterns worth checking." if signals else "These checks found no common patterns; they cannot establish that a message or sender is legitimate.",
        "next_step": "Open the organization's official app or contact it using a number you already know. Verify the request before sharing information, paying or opening a link.",
    }
