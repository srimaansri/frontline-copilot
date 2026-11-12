"""Dialogue templates for the synthetic transcripts.

A template is a list of ``(speaker, text)`` turns. ``{slot}`` markers are filled
by ``synth_transcripts.py``. Slots listed in ``SLOT_ENTITY`` are PII or CPNI: the
generator records the exact character span of each one as ground truth, so the
values must only ever enter the text through a slot.

The dialogues also contain numbers that are *not* personal data (plan prices,
"30 seconds", "7726", "300 minutes" as a plan feature). They are there on
purpose, as cases a redactor should leave alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Speaker = Literal["agent", "customer"]
Turn = tuple[Speaker, str]
Resolution = Literal["resolved", "escalated", "unresolved"]

# Slot name -> entity type recorded in the ground-truth labels.
SLOT_ENTITY: dict[str, str] = {
    "customer_name": "PERSON",
    "customer_name_lower": "PERSON",
    "customer_first": "PERSON",
    "agent_first": "PERSON",
    "other_name": "PERSON",
    "phone": "PHONE_NUMBER",
    "alt_phone": "PHONE_NUMBER",
    "called_number": "PHONE_NUMBER",
    "scam_number": "PHONE_NUMBER",
    "email": "EMAIL_ADDRESS",
    "address": "ADDRESS",
    "dob": "DATE_OF_BIRTH",
    "account_number": "ACCOUNT_NUMBER",
    "imei": "IMEI",
    "iccid": "ICCID",
    "ssn_last4": "SSN_LAST4",
    "credit_card": "CREDIT_CARD",
    "bill_amount": "CPNI_AMOUNT",
    "prev_bill_amount": "CPNI_AMOUNT",
    "usage_minutes": "CPNI_USAGE",
    "data_used": "CPNI_USAGE",
}

# Slots that are filled but are not personal data.
PLAIN_SLOTS: frozenset[str] = frozenset(
    {
        "plan_name",
        "plan_price",
        "new_plan_name",
        "new_plan_price",
        "country",
        "device",
        "ticket",
        "statement_date",
    }
)


@dataclass(frozen=True)
class Issue:
    """One way a conversation about a category can go."""

    intro: tuple[Turn, ...]
    body: tuple[Turn, ...]
    resolution: Resolution


# Category -> relative weight in the generated set.
CATEGORY_WEIGHTS: dict[str, int] = {
    "billing": 18,
    "troubleshooting": 16,
    "device_setup": 12,
    "plan_change": 12,
    "add_line": 8,
    "international": 8,
    "lost_stolen": 8,
    "cancel_port": 7,
    "accessibility": 6,
    "scam": 5,
}

OPENINGS: dict[str, tuple[tuple[Turn, ...], ...]] = {
    "call": (
        (
            (
                "agent",
                "Thank you for calling Northline Wireless, this is {agent_first}. "
                "How can I help you today?",
            ),
            ("customer", "Hi {agent_first}. My name is {customer_name} and I need some help."),
            ("agent", "Of course, {customer_first}. What's going on?"),
        ),
        (
            (
                "agent",
                "Northline Wireless support, {agent_first} speaking. Who do I have "
                "the pleasure of speaking with?",
            ),
            ("customer", "This is {customer_name}."),
            ("agent", "Thank you. What can I do for you today?"),
        ),
        (
            (
                "agent",
                "Good afternoon, you've reached Northline Wireless. My name is "
                "{agent_first}. May I have your name?",
            ),
            ("customer", "{customer_name}."),
            ("agent", "Thanks. How can I help?"),
        ),
        (
            ("agent", "Thanks for calling Northline. Can I get your first and last name?"),
            ("customer", "Yes, it's {customer_name}."),
            ("agent", "Hello {customer_first}, I'm {agent_first}. What brings you in today?"),
        ),
    ),
    "chat": (
        (
            (
                "agent",
                "Welcome to Northline chat support. I'm {agent_first}. How can I help you today?",
            ),
            ("customer", "hi, this is {customer_name}"),
            ("agent", "Hi {customer_first}! What can I do for you?"),
        ),
        (
            (
                "agent",
                "Hello, you're chatting with {agent_first} from Northline Wireless. "
                "May I have your name?",
            ),
            ("customer", "my name is {customer_name_lower}"),
            ("agent", "Thanks. What do you need help with?"),
        ),
        (
            ("agent", "Hi there, thanks for contacting Northline. Who am I chatting with?"),
            ("customer", "{customer_name}"),
            ("agent", "Nice to meet you. I'm {agent_first}. How can I help?"),
        ),
    ),
}

# Verification item -> (agent question, customer answer) variants. Several answers
# carry no cue word of their own ("{dob}."): the cue is in the agent's question.
VERIFICATION: dict[str, tuple[tuple[str, str], ...]] = {
    "account_number": (
        ("Can I have your account number, please?", "Sure, it's {account_number}."),
        ("What's the account number?", "{account_number}"),
        ("Could you read me your account number?", "My account number is {account_number}."),
    ),
    "dob": (
        ("And your date of birth?", "{dob}."),
        ("Can you confirm your date of birth for me?", "I was born on {dob}."),
        ("For security, what is your date of birth?", "My birthday is {dob}."),
    ),
    "ssn_last4": (
        ("Can I get the last four digits of your Social Security number?", "{ssn_last4}."),
        (
            "I'll need the last four of your social to verify.",
            "The last four of my social are {ssn_last4}.",
        ),
        ("Please confirm the last 4 of your SSN.", "It's {ssn_last4}."),
    ),
    "phone": (
        ("What is the phone number on the account?", "It's {phone}."),
        ("Which number are you calling about?", "My number is {phone}."),
        ("Can you confirm the mobile number?", "{phone}"),
    ),
    "address": (
        ("Can you confirm the billing address on file?", "It's {address}."),
        ("What is your home address?", "I live at {address}."),
        ("And the service address?", "{address}."),
    ),
    "email": (
        ("What email address do we have for you?", "It should be {email}."),
        ("Can I get an email for the confirmation?", "Yes, send it to {email}."),
        ("Is there an email on the account?", "{email}"),
    ),
}

VERIFY_LEAD_IN: tuple[str, ...] = (
    "Let me pull up your account. First I need to verify a few things.",
    "I can help with that. For your security, I have a couple of questions.",
    "Sure. Before I open the account I need to confirm who you are.",
)

ISSUES: dict[str, tuple[Issue, ...]] = {
    "billing": (
        Issue(
            intro=(
                ("customer", "My bill is higher than usual this month and I don't understand why."),
            ),
            body=(
                (
                    "agent",
                    "Thank you. I see your bill this month is {bill_amount}, and last "
                    "month it was {prev_bill_amount}.",
                ),
                (
                    "customer",
                    "Right, that's a big jump. I'm on the {plan_name} plan, which is "
                    "supposed to be {plan_price} a month.",
                ),
                (
                    "agent",
                    "I see what happened. You used {usage_minutes} of international "
                    "calling to {called_number}, and that was billed separately.",
                ),
                ("customer", "Oh, that's my sister in Canada. I didn't know that cost extra."),
                (
                    "agent",
                    "I can add the International Calling Pack for $5 a month. It "
                    "includes 300 minutes, so those calls are covered going forward.",
                ),
                ("customer", "Yes, please do that."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "I'd like to pay my bill over the phone."),),
            body=(
                ("agent", "Your balance due is {bill_amount}. Which card would you like to use?"),
                ("customer", "My Visa. The number is {credit_card}."),
                ("agent", "Thank you. And the billing address for that card?"),
                ("customer", "{address}."),
                ("agent", "The payment went through. Your confirmation number is {ticket}."),
                ("customer", "Great, thank you."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "There's a late fee on my bill and I always pay on time."),),
            body=(
                (
                    "agent",
                    "I see a Late Payment Fee of $5 on your statement dated {statement_date}.",
                ),
                (
                    "customer",
                    "I mailed the check on time. I owed {bill_amount} and I paid all of it.",
                ),
                (
                    "agent",
                    "I understand. I can't remove the fee myself, so I'm sending this "
                    "to our billing team to review. Your reference number is {ticket}.",
                ),
                ("customer", "Okay. How long will that take?"),
                (
                    "agent",
                    "Usually 3 to 5 business days. They'll call you at {phone} if they "
                    "need anything.",
                ),
            ),
            resolution="escalated",
        ),
    ),
    "troubleshooting": (
        Issue(
            intro=(("customer", "My phone has said no service since yesterday."),),
            body=(
                ("agent", "Thanks. What kind of phone do you have?"),
                ("customer", "It's a {device}."),
                ("agent", "Please turn the phone off, wait 30 seconds, and turn it back on."),
                ("customer", "Okay... it still says no service."),
                (
                    "agent",
                    "Let's check the SIM. Can you read me the long number printed on "
                    "the SIM card? It starts with 89.",
                ),
                ("customer", "It says {iccid}."),
                (
                    "agent",
                    "Thank you. I've refreshed the SIM on our side. Please restart once more.",
                ),
                ("customer", "It's working now! I see bars."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "People tell me their calls go straight to my voicemail."),),
            body=(
                (
                    "agent",
                    "Is Do Not Disturb turned on? Look for a moon icon at the top of the screen.",
                ),
                ("customer", "Yes, I see a moon."),
                ("agent", "Swipe down from the top and tap the moon to turn it off."),
                ("customer", "Okay, it's off. Can you call me to test? My number is {phone}."),
                ("agent", "Calling now. Did it ring?"),
                ("customer", "Yes, it rang. Thank you so much."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "My internet on the phone is very slow all of a sudden."),),
            body=(
                (
                    "agent",
                    "I see you've used {data_used} this month, which is over the "
                    "5 GB in your plan, so your data has slowed down.",
                ),
                ("customer", "I didn't realize I'd used that much."),
                (
                    "agent",
                    "You can add a Data Top-Up of 5 GB for $10, or wait until your "
                    "month resets on the 14th.",
                ),
                ("customer", "I'll just wait. Thank you."),
            ),
            resolution="unresolved",
        ),
    ),
    "device_setup": (
        Issue(
            intro=(("customer", "I just got a new phone and I need help setting it up."),),
            body=(
                (
                    "agent",
                    "Congratulations on the new phone. What's the IMEI? You can find "
                    "it by dialing star, pound, zero, six, pound.",
                ),
                ("customer", "Okay, it shows {imei}."),
                ("agent", "Got it. And the SIM card number, please?"),
                ("customer", "The SIM says {iccid}."),
                ("agent", "Thank you. Your {device} is now active on {phone}. Try making a call."),
                ("customer", "It works. Now how do I set up voicemail?"),
                (
                    "agent",
                    "Press and hold the 1 key, then follow the prompts to pick a PIN "
                    "and record your greeting.",
                ),
                ("customer", "Wonderful, thank you {agent_first}."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(
                (
                    "customer",
                    "I need to move my contacts and photos from my old phone to my new {device}.",
                ),
            ),
            body=(
                ("agent", "Do you have a Google or Apple account on the old phone?"),
                ("customer", "I think it's Google. My email is {email}."),
                (
                    "agent",
                    "Sign in with that same email on the new phone, and your contacts "
                    "will copy over.",
                ),
                ("customer", "They're showing up now. What about my photos?"),
                (
                    "agent",
                    "Turn on backup in the Photos app on the old phone first. It can "
                    "take an hour on Wi-Fi.",
                ),
                ("customer", "Okay, I'll try that tonight."),
            ),
            resolution="resolved",
        ),
    ),
    "plan_change": (
        Issue(
            intro=(("customer", "I want to switch to a cheaper plan."),),
            body=(
                (
                    "agent",
                    "You're on {plan_name} at {plan_price} a month. Over the last "
                    "three months you used about {data_used} a month.",
                ),
                ("customer", "So I'm paying for more than I use?"),
                (
                    "agent",
                    "Yes. The {new_plan_name} plan is {new_plan_price} a month and "
                    "would cover that.",
                ),
                ("customer", "Let's do that one."),
                (
                    "agent",
                    "I'm not able to change the plan from this desk, so I'm passing "
                    "this to our account team. They will call you back at {alt_phone} "
                    "today.",
                ),
                ("customer", "That's fine. Thank you."),
            ),
            resolution="escalated",
        ),
        Issue(
            intro=(("customer", "My grandkids use up all my data. Can I get unlimited?"),),
            body=(
                (
                    "agent",
                    "Sure. Northline Unlimited Essentials is $50 a month. Your last "
                    "bill was {bill_amount}.",
                ),
                ("customer", "And when would it start?"),
                (
                    "agent",
                    "On your next billing date. Our account team makes the change. "
                    "Your reference number is {ticket}.",
                ),
                ("customer", "Thank you, dear."),
            ),
            resolution="escalated",
        ),
    ),
    "add_line": (
        Issue(
            intro=(("customer", "I'd like to add a line for my husband."),),
            body=(
                ("agent", "I can help. What's his full name?"),
                ("customer", "{other_name}."),
                ("agent", "And does he have a phone already?"),
                ("customer", "Yes, an old {device}. The IMEI is {imei}."),
                ("agent", "An Extra Line is $15 a month, plus a one-time Activation Fee of $35."),
                ("customer", "That's fine."),
                ("agent", "Would he like a new number, or to bring his number over?"),
                ("customer", "He wants to keep his number. It's {alt_phone}."),
                ("agent", "I've started the transfer. It usually finishes within 24 hours."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "Can I put my daughter on my plan?"),),
            body=(
                ("agent", "Yes. An Extra Line is $15 a month. What is her name?"),
                ("customer", "Her name is {other_name}."),
                ("agent", "Thank you. Where should I send the new SIM card?"),
                ("customer", "Send it to her, at {address}."),
                ("agent", "Done. I'll email the tracking number. Which email should I use?"),
                ("customer", "{email}"),
                ("agent", "It's on the way. Order number {ticket}."),
            ),
            resolution="resolved",
        ),
    ),
    "international": (
        Issue(
            intro=(("customer", "I'm going to {country} next month. Will my phone work there?"),),
            body=(
                (
                    "agent",
                    "Yes. The International Day Pass is $10 a day, and you're only "
                    "charged on days you use the phone.",
                ),
                ("customer", "We'll be there from the 3rd to the 17th."),
                ("agent", "Then the most you would pay is $150. Would you like me to add it?"),
                ("customer", "Yes please. Will people still reach me at {phone}?"),
                (
                    "agent",
                    "Yes, your number stays the same. I've added the pass and sent a "
                    "confirmation to {email}.",
                ),
                ("customer", "Perfect."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "How much does it cost to call my son in {country}?"),),
            body=(
                (
                    "agent",
                    "Without a pack, calls are billed by the minute. Last month you "
                    "made {usage_minutes} of calls to {called_number}.",
                ),
                ("customer", "Yes, that's his number."),
                ("agent", "The International Calling Pack is $5 a month for 300 minutes."),
                ("customer", "Add that, please."),
            ),
            resolution="resolved",
        ),
    ),
    "lost_stolen": (
        Issue(
            intro=(
                ("customer", "My phone was stolen this morning. I need it turned off right away."),
            ),
            body=(
                ("agent", "I'm so sorry. I'm suspending the line now so no one can use it."),
                ("customer", "Thank you. Can they get into my account?"),
                (
                    "agent",
                    "No. I've also blocked the device. For the record, the IMEI we "
                    "have on file is {imei}.",
                ),
                ("customer", "What do I do about a new phone?"),
                (
                    "agent",
                    "I see Device Protection on your account. Our claims team will "
                    "call you. What's a good number to reach you?",
                ),
                ("customer", "Call my wife's phone, {alt_phone}. Her name is {other_name}."),
                ("agent", "Got it. The claim number is {ticket}."),
            ),
            resolution="escalated",
        ),
        Issue(
            intro=(("customer", "I lost my phone at the grocery store yesterday."),),
            body=(
                (
                    "agent",
                    "I can suspend service so nobody runs up charges. Is {phone} the "
                    "line that's lost?",
                ),
                ("customer", "Yes, that one."),
                (
                    "agent",
                    "It's suspended. If you find it, call us and we'll turn it back on right away.",
                ),
                ("customer", "Can I get a new SIM in the meantime?"),
                ("agent", "Yes. I can mail one to {address}. Is that still right?"),
                ("customer", "Yes, please send it there."),
            ),
            resolution="resolved",
        ),
    ),
    "cancel_port": (
        Issue(
            intro=(
                ("customer", "I want to cancel my service and move my number to another company."),
            ),
            body=(
                ("agent", "I'm sorry to hear that. May I ask why?"),
                ("customer", "My bill went up to {bill_amount} and my neighbor pays less."),
                (
                    "agent",
                    "I understand. To move your number, the new company will need a "
                    "transfer PIN. I can't give that out on this call, so I'm sending "
                    "you to our account security team.",
                ),
                ("customer", "How long will that take?"),
                ("agent", "They'll call you at {phone} within one business day."),
                ("customer", "All right."),
            ),
            resolution="escalated",
        ),
        Issue(
            intro=(("customer", "My husband passed away and I need to cancel his line."),),
            body=(
                ("agent", "I'm very sorry for your loss. I can help. What was his name?"),
                ("customer", "{other_name}."),
                ("agent", "And his phone number?"),
                ("customer", "{alt_phone}."),
                ("agent", "Thank you. Our account team handles this. Can they email you?"),
                ("customer", "Yes, {email}."),
                (
                    "agent",
                    "I've opened case {ticket}. Someone will contact you within two business days.",
                ),
            ),
            resolution="escalated",
        ),
    ),
    "accessibility": (
        Issue(
            intro=(("customer", "I wear hearing aids and I can't hear well on my new phone."),),
            body=(
                ("agent", "Many phones have a hearing aid setting. What phone do you have?"),
                ("customer", "A {device}."),
                (
                    "agent",
                    "Go to Settings, then Accessibility, then Hearing Devices, and "
                    "turn on Hearing Aid Compatibility.",
                ),
                ("customer", "Okay, I found it. It's on now."),
                ("agent", "Let me call you to test. Is {phone} the best number?"),
                ("customer", "Yes."),
                ("agent", "How does that sound?"),
                ("customer", "Much clearer. Thank you, {agent_first}."),
            ),
            resolution="resolved",
        ),
        Issue(
            intro=(("customer", "The words on my screen are too small to read."),),
            body=(
                ("agent", "We can make them bigger. Open Settings and tap Display."),
                ("customer", "Okay."),
                ("agent", "Tap Font Size and drag the slider to the right."),
                ("customer", "Oh, that's much better."),
                ("agent", "I can also email you a large-print guide. What's your email?"),
                ("customer", "{email}"),
                ("agent", "Sent. It should arrive in a few minutes."),
            ),
            resolution="resolved",
        ),
    ),
    "scam": (
        Issue(
            intro=(
                (
                    "customer",
                    "I got a text saying my account is locked and to click a "
                    "link. Is that from you?",
                ),
            ),
            body=(
                (
                    "agent",
                    "No, that is not from us. Please do not click the link. What "
                    "number did it come from?",
                ),
                ("customer", "It came from {scam_number}."),
                ("agent", "Thank you. Did you reply or give them any information?"),
                ("customer", "I'm afraid I typed in my card number, {credit_card}."),
                (
                    "agent",
                    "Please call your bank right away to cancel that card. I'm "
                    "reporting the number and adding a note to your account.",
                ),
                ("customer", "Oh dear. Thank you for telling me."),
                ("agent", "You can forward scam texts to 7726. That's free."),
            ),
            resolution="unresolved",
        ),
        Issue(
            intro=(
                (
                    "customer",
                    "Someone called claiming to be from Northline and asked "
                    "for my Social Security number.",
                ),
            ),
            body=(
                (
                    "agent",
                    "We will never call and ask for your full Social Security number. "
                    "Did you give it to them?",
                ),
                ("customer", "Only the last four, {ssn_last4}."),
                ("agent", "Okay. What number did they call from?"),
                ("customer", "{scam_number}."),
                (
                    "agent",
                    "I've reported it. I'm also adding extra security. From now on we "
                    "will ask for a PIN when you call.",
                ),
                ("customer", "Thank you. That makes me feel better."),
            ),
            resolution="resolved",
        ),
    ),
}

CLOSINGS: dict[str, dict[Resolution, tuple[tuple[Turn, ...], ...]]] = {
    "call": {
        "resolved": (
            (
                ("agent", "Is there anything else I can help you with today?"),
                ("customer", "No, that's everything. Thank you."),
            ),
            (
                ("agent", "You're all set, {customer_first}. Have a great day."),
                ("customer", "You too. Bye."),
            ),
        ),
        "escalated": (
            (
                (
                    "agent",
                    "I've noted everything so you won't have to repeat it. Is there anything else?",
                ),
                ("customer", "No, thank you for your help."),
            ),
        ),
        "unresolved": (
            (
                (
                    "agent",
                    "I'm sorry we couldn't do more today. Please call back if anything changes.",
                ),
                ("customer", "Okay. Goodbye."),
            ),
        ),
    },
    "chat": {
        "resolved": (
            (
                ("agent", "Thanks for chatting with Northline today, {customer_first}."),
                ("customer", "thanks!"),
            ),
        ),
        "escalated": (
            (
                ("agent", "I've added notes to the case so the next team has the details."),
                ("customer", "ok thank you"),
            ),
        ),
        "unresolved": (
            (
                ("agent", "Sorry I couldn't do more. You can chat with us again any time."),
                ("customer", "ok"),
            ),
        ),
    },
}
