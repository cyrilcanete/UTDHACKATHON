"""Explain common message warning signs without visiting links or executing instructions."""
import re


SAMPLES = [
    {"id": "delivery", "title": "Parcel redelivery fee", "text": "URGENT: Your parcel is on hold. Pay a small redelivery fee now at https://parcel-support.invalid/verify or your package will be returned."},
    {"id": "code", "title": "Account verification request", "text": "This is account support. Tell me your one-time verification code immediately so we can stop your account from being suspended."},
    {"id": "ordinary", "title": "Project meeting reminder", "text": "Hi! Our project meeting is at 3 PM in the library. Please bring your notes. See you there."},
    {"id": "prize", "title": "Free prize — claim today", "text": "Last chance! Act now to claim your free prize. Pay a processing fee at https://rewards-center.invalid and send your verification code."},
    {"id": "promotion", "title": "Library workshop invitation", "text": "Free library workshop this Saturday. Register at the library front desk. No payment required."},
]


def review_message(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("Enter a message between 1 and 4,000 characters")
    rules = [
        (r"\bfree\b", "Free offer", "Free offers are common in legitimate promotions too. Check whether this offer also asks for money, codes or personal information."),
        (r"\b(urgent|immediately|act now|last chance|right now|suspend\w*|within \d+|will be returned)\b", "Pressure or threatened consequences", "Pressure can discourage you from checking the request independently."),
        (r"\b(password|verification code|one[- ]time (?:password|code)|otp|social security|ssn)\b", "Sensitive information or verification codes", "A request to share credentials or codes deserves independent verification."),
        (r"\b(pay|payment|fee|gift cards?|wire transfer|crypto\w*|bank details)\b", "Money or payment request", "Confirm payment requests through a channel you already trust."),
        (r"https?://|www\.", "External link", "A link alone does not prove fraud. Verify the destination through the organization's official app or a known address."),
    ]
    signals = [{"title": title, "detail": detail, "matches": list(dict.fromkeys(m.group(0).lower() for m in re.finditer(pattern, text, re.I)))} for pattern, title, detail in rules if re.search(pattern, text, re.I)]
    lower = text.lower()
    if re.search(r"\b(password|verification code|one[- ]time (?:password|code)|otp)\b", lower):
        next_step = "Do not reply with a password or verification code. Open the account's official app yourself and check its security notifications."
    elif re.search(r"\b(parcel|delivery|redelivery)\b", lower):
        next_step = "Do not pay through this message. Open the carrier's official app and enter the tracking number from your original order."
    elif re.search(r"\b(free|prize|gift card)\b", lower):
        next_step = "Do not pay a fee to claim the offer. Open the company's official app yourself and check whether the promotion exists."
    else:
        next_step = "Contact the sender using a number or account you already know before acting on this request."
    return {
        "excerpt": re.sub(r"\b\d{6,8}\b", "[code redacted]", text[:650]),
        "risk": "multiple warning signs" if len(signals) >= 2 else "check context" if signals else "no pattern found",
        "method": "Rule-based review · AI is not used for this result",
        "verdict": "Review before acting" if signals else "No common warning signs detected",
        "signals": signals,
        "summary": "This message contains patterns worth checking." if signals else "These checks found no common patterns; they cannot establish that a message or sender is legitimate.",
        "next_step": next_step,
    }

# Read-only Gmail search; matches are leads for review, not a fraud determination.
PHISHING_QUERY = 'in:inbox newer_than:30d {free "last chance" "act now" urgent "verification code" "gift card"}'
GUIDANCE_URL = "https://consumer.ftc.gov/articles/how-recognize-avoid-phishing-scams"

def review_inbox_messages(messages):
    results = []
    for message in messages:
        text = (message.get("subject", "") + "\n" + message.get("body", ""))[:4000]
        if not text.strip():
            continue
        review = review_message(text)
        if review["signals"]:
            results.append({"id": message["id"], "subject": message.get("subject", "(No subject)"),
                            "sender": message.get("sender", "Unknown"), "review": review})
    return results
