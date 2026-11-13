"""Topics for the synthetic knowledge base.

Each topic carries a brief: the facts the article must state. The language model
writes the prose, but every price, fee, limit and phone number comes from here
or from the plan catalogue, so the articles agree with each other and with
``plans.csv``. Everything about "Northline Wireless" is invented.
"""

from __future__ import annotations

from dataclasses import dataclass

SECTIONS: tuple[str, ...] = ("Billing", "Plans", "Devices", "Account", "Troubleshooting", "Other")

# Facts that apply to every article.
CARRIER_FACTS: tuple[str, ...] = (
    "The carrier is Northline Wireless. It is a fictional company.",
    "Customers reach support by dialing 611 from a Northline phone, or 1-800-555-0199 from "
    "any phone. Support is open 7 a.m. to 9 p.m. Central Time, every day.",
    "Customers manage their account in the My Northline app or at northline.example.",
    "Northline has no contracts and no early termination fee.",
    "Bills are monthly and are charged in advance for the month ahead.",
)


@dataclass(frozen=True)
class Topic:
    """One article to write."""

    slug: str
    title: str
    section: str
    brief: str


def _t(slug: str, title: str, section: str, brief: str) -> Topic:
    return Topic(slug, title, section, brief)


TOPICS: tuple[Topic, ...] = (
    # --- Billing --------------------------------------------------------------------
    _t("read-your-bill", "How to read your bill", "Billing",
       "A bill has four parts: plan charges, add-ons, one-time fees, and taxes. The statement "
       "date is the day the bill is created. The due date is 21 days after the statement date. "
       "The bill is in the My Northline app under Billing."),
    _t("pay-your-bill", "Ways to pay your bill", "Billing",
       "Pay in the My Northline app, at northline.example, by phone by dialing 611 (the "
       "automated payment line is free), or by mailing a check. Allow 7 days for a mailed "
       "check to arrive. Cards and bank accounts are accepted."),
    _t("set-up-autopay", "Set up AutoPay", "Billing",
       "AutoPay charges the default payment method on the due date. It is free. Turn it on in "
       "the app under Billing, then AutoPay. To change or turn it off, do so at least 2 days "
       "before the due date."),
    _t("late-payment-fee", "Late payment fee", "Billing",
       "A Late Payment Fee of $5 is charged when a bill is more than 10 days past due. Service "
       "may be suspended when a bill is 30 days past due. A customer can ask support for a "
       "one-time waiver; the billing team reviews the request."),
    _t("paper-bill-fee", "Paper bills and email bills", "Billing",
       "A mailed paper bill costs $2 a month. Email bills are free. Switch in the app under "
       "Billing, then Bill delivery. Large-print bills are free on request."),
    _t("payment-arrangement", "If you cannot pay on time", "Billing",
       "Ask for a payment arrangement before the due date. It gives up to 14 extra days. It "
       "must be set up by contacting support, because the billing team has to approve it. No "
       "Late Payment Fee is charged during an approved arrangement."),
    _t("bill-higher-than-expected", "Why your bill is higher than usual", "Billing",
       "Common reasons: a one-time fee such as the $35 Activation Fee or the $10 SIM "
       "Replacement Fee, a new add-on, days abroad on the International Day Pass at $10 a day, "
       "a plan change in the middle of a month, or the $5 Late Payment Fee."),
    _t("your-first-bill", "Your first bill explained", "Billing",
       "The first bill is usually higher. It includes the $35 Activation Fee for each new "
       "line, a partial month from the start date to the first statement date, and the full "
       "month ahead, because plans are billed in advance."),
    _t("refunds", "Refunds and credit balances", "Billing",
       "A refund goes back to the original payment method in 5 to 7 business days. A credit "
       "balance stays on the account and is applied to the next bill."),
    _t("update-payment-method", "Update your payment method", "Billing",
       "Add, remove or change a card or bank account in the app under Billing, then Payment "
       "methods. AutoPay always uses the method marked as default. Update an expired card "
       "before the due date."),
    _t("taxes-and-surcharges", "Taxes on your bill", "Billing",
       "Taxes are set by federal, state and local governments and depend on the billing "
       "address. Northline does not add administrative fees beyond the fees in its price "
       "list. Taxes can change when the address changes."),
    _t("billing-cycle-and-due-date", "Your billing date and due date", "Billing",
       "The statement date is the same day every month. The due date is 21 days later. A "
       "customer can ask support to change the statement date once every 12 months."),
    _t("dispute-a-charge", "Dispute a charge", "Billing",
       "Contact support within 60 days of the statement date. The billing team reviews the "
       "dispute in 3 to 5 business days. Keep paying the rest of the bill while the dispute is "
       "reviewed."),
    _t("restore-suspended-service", "Service suspended for non-payment", "Billing",
       "Service may be suspended when a bill is 30 days past due. Paying the past-due balance "
       "restores service within 1 hour. There is no reconnection fee. Emergency calls to 911 "
       "still work while suspended."),
    # --- Plans ----------------------------------------------------------------------
    _t("compare-plans", "Compare Northline plans", "Plans",
       "List all eight plans with their monthly price and data amount, using only the plan "
       "list. Every plan includes unlimited talk and text."),
    _t("choose-the-right-plan", "Choose the right plan", "Plans",
       "Suggest a plan by use: calls and texts only, Northline Talk; email and maps, Starter "
       "1; everyday browsing, Everyday 5 or Plus 10; video and music, Extra 20 or an unlimited "
       "plan; two people, Two-Line Unlimited. Check usage in the app first."),
    _t("change-your-plan", "Change your plan", "Plans",
       "A plan change takes effect on the next billing date. There is no fee to change plans. "
       "The account owner can ask for it in the app under Plan, or through support. The "
       "account team makes the change."),
    _t("unlimited-data-explained", "How unlimited data works", "Plans",
       "On Unlimited Essentials, speeds may slow after 35 GB in a month. On Unlimited Premium, "
       "after 60 GB. Speeds return to normal on the next billing date. Hotspot data is "
       "separate: 5 GB on Essentials, 30 GB on Premium."),
    _t("add-a-line", "Add a line to your account", "Plans",
       "An Extra Line costs $15 a month plus a one-time $35 Activation Fee. An account can "
       "have up to 5 lines. An Extra Line cannot be added to Two-Line Unlimited. The new line "
       "can use a new number or bring an existing number."),
    _t("two-line-unlimited", "Two-Line Unlimited", "Plans",
       "Two-Line Unlimited is $80 a month for both lines together. Both lines share unlimited "
       "data and 10 GB of hotspot data. It includes calls to Canada and Mexico."),
    _t("data-top-up", "Add more data with a Data Top-Up", "Plans",
       "Data Top-Up 5 adds 5 GB for a one-time $10. The data lasts until the end of the "
       "billing month and does not carry over. Buy it in the app under Plan, then Add-ons."),
    _t("hotspot-boost", "Hotspot Boost", "Plans",
       "Hotspot Boost adds 10 GB of hotspot data each month for $10 a month. It works with any "
       "plan that includes mobile data. Northline Talk has no data, so it cannot use a "
       "hotspot."),
    _t("check-data-usage", "Check your data usage", "Plans",
       "See usage in the app under Usage, or text USAGE to 611 for free. Northline sends a "
       "text alert at 75% and at 100% of the monthly data."),
    _t("international-day-pass", "International Day Pass", "Plans",
       "The International Day Pass is $10 a day. It works in over 100 countries. A day is "
       "charged only when the phone is used abroad, and one day covers 24 hours from first "
       "use. Calls, texts and data come from the regular plan."),
    _t("international-calling-pack", "International Calling Pack", "Plans",
       "The International Calling Pack is $5 a month. It includes 300 minutes of calls from "
       "the United States to 60 countries. It is for calling abroad from home, not for "
       "travelling."),
    _t("canada-and-mexico", "Using your phone in Canada and Mexico", "Plans",
       "Unlimited Premium includes calls and roaming in Canada and Mexico. Plus 10, Extra 20, "
       "Unlimited Essentials and Two-Line Unlimited include calls from the United States to "
       "Canada and Mexico, but not roaming there; use the International Day Pass at $10 a day "
       "when travelling."),
    _t("before-you-travel", "Before you travel abroad", "Plans",
       "Add the International Day Pass at $10 a day before leaving. Turn on data roaming in "
       "the phone settings on arrival. Wi-Fi calling to United States numbers is free. Save "
       "1-800-555-0199 for support from abroad."),
    _t("device-protection", "Device Protection", "Plans",
       "Device Protection is $9 a month. It covers loss, theft and damage. A deductible "
       "applies to each claim and is shown in the app. A device must be enrolled within 30 "
       "days of activation. The claims team handles claims."),
    _t("northline-talk-plan", "The Northline Talk plan", "Plans",
       "Northline Talk is $15 a month with unlimited talk and text and no mobile data. The "
       "phone can still use Wi-Fi for the internet. It cannot be used as a hotspot."),
    _t("remove-an-add-on", "Remove an add-on", "Plans",
       "Remove an add-on in the app under Plan, then Add-ons. It stays active until the end of "
       "the billing month. There is no partial refund for the unused part of the month."),
    # --- Devices --------------------------------------------------------------------
    _t("activate-a-new-phone", "Activate a new phone", "Devices",
       "Insert the SIM card or choose eSIM, turn the phone on, then activate in the app or at "
       "northline.example/activate. The IMEI and the SIM card number are needed. Activation "
       "can take up to 15 minutes."),
    _t("find-your-imei", "Find your phone's IMEI", "Devices",
       "Dial *#06# to show the 15-digit IMEI. It is also in Settings under About phone, and on "
       "the original box. The IMEI identifies the device, so share it only with support."),
    _t("sim-and-esim", "SIM cards and eSIM", "Devices",
       "A SIM card is a small chip that links the phone to the account. An eSIM is built into "
       "the phone and needs no chip. Switching to eSIM is free. A replacement SIM card costs "
       "$10."),
    _t("replace-a-sim-card", "Replace a SIM card", "Devices",
       "Order a replacement in the app under Devices or through support. The SIM Replacement "
       "Fee is $10. It arrives in 3 to 5 business days. An eSIM replacement is free and works "
       "right away."),
    _t("switch-to-esim", "Switch to eSIM", "Devices",
       "In the app go to Devices, then Switch to eSIM, and follow the steps. It is free. The "
       "phone must be on Wi-Fi. The old SIM card stops working once the eSIM is active."),
    _t("set-up-voicemail", "Set up voicemail", "Devices",
       "Press and hold the 1 key. Choose a voicemail PIN of 4 to 6 digits. Record a greeting. "
       "The mailbox holds 30 messages, and each message is kept for 30 days."),
    _t("reset-voicemail-pin", "Reset your voicemail PIN", "Devices",
       "In the app go to Devices, then Voicemail, then Reset PIN. Or dial 611. The new PIN "
       "must be 4 to 6 digits."),
    _t("move-contacts-and-photos", "Move contacts and photos to a new phone", "Devices",
       "Sign in to the same Google or Apple account on the new phone and turn on sync for "
       "contacts. Turn on photo backup on the old phone first. Photo backup can take an hour "
       "or more on Wi-Fi."),
    _t("wifi-calling", "Wi-Fi calling", "Devices",
       "Wi-Fi calling lets the phone call and text over Wi-Fi where the signal is weak. Turn "
       "it on in the phone settings. An emergency address must be entered. Calls to United "
       "States numbers are free, including from abroad."),
    _t("bring-your-own-phone", "Bring your own phone", "Devices",
       "Check compatibility at northline.example/byod using the IMEI. The phone must be "
       "unlocked by its previous carrier. A new line has a $35 Activation Fee."),
    _t("unlock-your-phone", "Unlock a Northline phone", "Devices",
       "A phone bought from Northline can be unlocked after 60 days of paid service. The "
       "account owner asks support, and the account team completes the unlock in 2 business "
       "days. There is no fee."),
    _t("set-up-mobile-hotspot", "Use your phone as a hotspot", "Devices",
       "Turn on Hotspot in the phone settings and set a password. Hotspot data comes from the "
       "plan's hotspot amount. When it is used up, the hotspot stops until the next billing "
       "date unless Hotspot Boost is added."),
    _t("block-unwanted-calls", "Block unwanted calls", "Devices",
       "Block a number from the recent calls list on the phone. Northline Call Filter is free "
       "and is turned on in the app under Security. It labels likely spam calls."),
    _t("back-up-your-phone", "Back up your phone", "Devices",
       "Use iCloud on an iPhone or Google backup on Android. Back up on Wi-Fi with the phone "
       "charging. A backup makes it easy to restore everything on a new or replacement "
       "phone."),
    _t("update-phone-software", "Update your phone's software", "Devices",
       "Go to Settings, then Software update. Connect to Wi-Fi and have at least 50% battery. "
       "Updates fix problems and improve security. The phone restarts during the update."),
    _t("return-a-device", "Return or exchange a device", "Devices",
       "A device bought from Northline can be returned within 30 days in its original "
       "condition. There is no restocking fee. Start a return through support. The refund "
       "arrives 5 to 7 business days after the device is received."),
    # --- Account --------------------------------------------------------------------
    _t("create-online-account", "Create your online account", "Account",
       "Register at northline.example/register or in the My Northline app. Enter the phone "
       "number, then the one-time code sent by text. The code expires in 10 minutes."),
    _t("reset-your-password", "Reset your password", "Account",
       "Choose Forgot password on the sign-in page. A one-time code is sent by text and "
       "expires in 10 minutes. After 5 wrong attempts the account is locked for 30 minutes."),
    _t("account-pin", "Your account PIN", "Account",
       "The account PIN is 4 to 6 digits. Support asks for it to confirm identity on a call. "
       "Set or change it in the app under Security. Northline will never call, text or email "
       "to ask for the PIN."),
    _t("authorized-users", "Add an authorized user", "Account",
       "The account owner can add an authorized user in the app under Security, then "
       "Authorized users. An authorized user can ask about billing and get technical help, "
       "but cannot cancel service, transfer a number or change the owner."),
    _t("update-contact-details", "Update your address or email", "Account",
       "Change the address or email in the app under Profile. The billing address affects "
       "taxes. A confirmation is sent to both the old and the new email address."),
    _t("transfer-number-to-northline", "Bring your number to Northline", "Account",
       "The account number and transfer PIN from the old carrier are needed. Keep the old "
       "service active until the transfer finishes. A mobile number usually takes up to 24 "
       "hours; a landline can take up to 10 business days."),
    _t("transfer-number-away", "Move your number to another carrier", "Account",
       "The new carrier needs the Northline account number and a transfer PIN. The account "
       "owner gets the transfer PIN in the app under Security, then Transfer PIN. It is valid "
       "for 7 days. Support agents cannot read a transfer PIN out on a call; the account "
       "security team handles requests."),
    _t("change-your-phone-number", "Change your phone number", "Account",
       "A number can be changed for free once every 12 months. The account owner asks "
       "support. The old number stops working right away, and voicemail messages are not "
       "moved."),
    _t("cancel-service", "Cancel your service", "Account",
       "Only the account owner can cancel. Service ends at the end of the billing month. "
       "There is no early termination fee. A final bill is sent, and any credit is refunded "
       "in 5 to 7 business days."),
    _t("deceased-account-holder", "When an account holder has died", "Account",
       "The account team helps with this and may ask for a copy of the death certificate. The "
       "service can be cancelled, or ownership can be moved to a family member. Contact "
       "support to open a case; a reply comes within 2 business days."),
    _t("transfer-ownership", "Transfer account ownership", "Account",
       "Both the current owner and the new owner must agree. The account team completes the "
       "transfer in 3 to 5 business days. The new owner becomes responsible for the bill."),
    _t("lost-or-stolen-phone", "Lost or stolen phone", "Account",
       "Suspend the line right away in the app under Devices, then Suspend, or call "
       "1-800-555-0199 from another phone. Northline blocks the device by its IMEI. With "
       "Device Protection, the claims team handles a replacement. A replacement SIM card "
       "costs $10."),
    _t("number-lock", "Protect your number with Number Lock", "Account",
       "Number Lock is free and is turned on in the app under Security. While it is on, the "
       "number cannot be moved to another carrier or another SIM. Turn it off only when "
       "making a transfer yourself."),
    _t("pause-your-service", "Pause your service", "Account",
       "Service can be paused for up to 90 days in a 12-month period, for example during a "
       "long trip. The account owner asks support. The number is kept. Calls, texts and data "
       "do not work while paused."),
    # --- Troubleshooting ------------------------------------------------------------
    _t("no-service", "Phone shows no service", "Troubleshooting",
       "Restart the phone. Turn airplane mode on and off. Check for an outage at "
       "northline.example/outage. Remove and reinsert the SIM card. Check that the bill is "
       "not past due. If none of these help, contact support."),
    _t("calls-go-to-voicemail", "Calls go straight to voicemail", "Troubleshooting",
       "Check that Do Not Disturb is off (a moon icon shows when it is on). Check that "
       "airplane mode is off and call forwarding is off. Check that the caller is not on the "
       "blocked list."),
    _t("slow-data", "Mobile data is slow", "Troubleshooting",
       "Check usage in the app: data slows after the plan's monthly amount is used. Restart "
       "the phone. Use Wi-Fi where possible. A Data Top-Up of 5 GB for $10 restores full "
       "speed until the end of the billing month."),
    _t("cannot-send-texts", "Cannot send or receive texts", "Troubleshooting",
       "Check the signal. Restart the phone. Make sure the number is typed with its area "
       "code. Free up storage if the phone is full. Picture messages need mobile data to be "
       "turned on."),
    _t("cannot-make-calls", "Cannot make calls", "Troubleshooting",
       "Check that airplane mode is off and the phone shows signal bars. Check that the bill "
       "is not 30 days past due. Restart the phone. Try Wi-Fi calling if the signal is weak "
       "indoors."),
    _t("dropped-calls", "Calls keep dropping", "Troubleshooting",
       "Turn on Wi-Fi calling for use indoors. Update the phone's software. Check coverage at "
       "northline.example/coverage. Note where and when calls drop, and tell support."),
    _t("phone-will-not-turn-on", "Phone will not turn on", "Troubleshooting",
       "Charge the phone for at least 30 minutes with a cable that is known to work. Then "
       "press and hold the power button for 20 seconds. If it still does not start and the "
       "phone has Device Protection, the claims team can help."),
    _t("voicemail-not-working", "Voicemail is not working", "Troubleshooting",
       "A full mailbox cannot take new messages: it holds 30 messages. Delete old ones. Reset "
       "the voicemail PIN in the app under Devices, then Voicemail. Check that call "
       "forwarding is off."),
    _t("hotspot-not-working", "Hotspot is not working", "Troubleshooting",
       "Check that the plan includes hotspot data; Northline Talk, Starter 1 and Everyday 5 "
       "do not. Check in the app whether the month's hotspot data is used up. Turn the "
       "hotspot off and on, and re-enter the password on the other device."),
    _t("no-service-abroad", "Phone does not work abroad", "Troubleshooting",
       "Check that the International Day Pass is on the account. Turn on data roaming in the "
       "phone settings. Restart the phone. If it still does not connect, choose a network by "
       "hand in the mobile network settings."),
    _t("esim-activation-failed", "eSIM will not activate", "Troubleshooting",
       "Connect to Wi-Fi. Restart the phone and try again from the app under Devices. "
       "Activation can take up to 15 minutes. If it fails twice, contact support and have "
       "the IMEI ready."),
    _t("sim-not-detected", "SIM card not detected", "Troubleshooting",
       "Turn the phone off. Remove the SIM card, wipe it gently with a dry cloth, and put it "
       "back. If another phone also cannot read it, the card is faulty. A replacement SIM "
       "card costs $10; an eSIM is free."),
    _t("wifi-calling-not-working", "Wi-Fi calling is not working", "Troubleshooting",
       "Check that Wi-Fi calling is on in the phone settings and that an emergency address is "
       "saved. Connect to a different Wi-Fi network to test. Update the phone's software and "
       "restart."),
    _t("cannot-sign-in", "Cannot sign in to your account", "Troubleshooting",
       "Reset the password with Forgot password. After 5 wrong attempts the account is locked "
       "for 30 minutes. If the one-time code does not arrive, check the signal and ask for a "
       "new code; each code expires in 10 minutes."),
    _t("verification-codes-not-arriving", "Not receiving verification codes", "Troubleshooting",
       "Restart the phone and check the signal. Check that short code messages are not "
       "blocked in the messaging app. Ask for a new code; each code expires in 10 minutes. "
       "Never share a code with anyone who calls you."),
    _t("app-not-working", "The My Northline app is not working", "Troubleshooting",
       "Update the app from the app store. Close it fully and open it again. Restart the "
       "phone. If it still fails, remove and reinstall it. The same tasks can be done at "
       "northline.example."),
    # --- Other ----------------------------------------------------------------------
    _t("spot-a-scam-text", "Spot a scam text", "Other",
       "Northline never asks for a PIN, password or card number by text. Do not click links "
       "in an unexpected text. Forward the text to 7726, which is free, then delete it."),
    _t("scam-calls", "Calls pretending to be Northline", "Other",
       "Northline will never call to ask for a full Social Security number, an account PIN or "
       "a verification code. Hang up and dial 611. If information was shared, change the "
       "account PIN in the app and turn on Number Lock."),
    _t("accessibility-services", "Accessibility services", "Other",
       "Large-print and braille bills are free on request. Support can be reached through "
       "the 711 relay service. Real-time text is supported on most recent phones."),
    _t("hearing-aid-compatibility", "Hearing aid compatibility", "Other",
       "Many phones are rated for use with hearing aids; look for an M3 or T4 rating or "
       "higher. Turn on the hearing aid setting under Accessibility in the phone settings. A "
       "phone can be returned within 30 days if it does not work well with a hearing aid."),
    _t("pair-hearing-aids", "Connect hearing aids by Bluetooth", "Other",
       "Turn on Bluetooth. Open Accessibility, then Hearing devices, in the phone settings. "
       "Put the hearing aids in pairing mode, usually by opening and closing the battery "
       "door. Choose them on the phone's list."),
    _t("make-text-larger", "Make the screen easier to read", "Other",
       "Go to Settings, then Display, then Font size, and move the slider. Display size makes "
       "everything larger. Bold text and high contrast are under Accessibility."),
    _t("screen-reader", "Use a screen reader", "Other",
       "TalkBack on Android and VoiceOver on iPhone read the screen aloud. Turn them on under "
       "Accessibility in the phone settings. The My Northline app works with both."),
    _t("contact-support", "Contact Northline support", "Other",
       "Dial 611 from a Northline phone or 1-800-555-0199 from any phone. Chat is in the My "
       "Northline app. Support is open 7 a.m. to 9 p.m. Central Time, every day. Have the "
       "account PIN ready."),
    _t("coverage-map", "Check coverage in your area", "Other",
       "Enter an address at northline.example/coverage to see coverage. Coverage indoors can "
       "be weaker than the map shows. Wi-Fi calling helps where indoor signal is weak."),
    _t("emergency-calls", "Calling 911", "Other",
       "Calls to 911 work even when service is suspended or the plan has no minutes left. On "
       "Wi-Fi calling, 911 uses the emergency address saved in the phone settings, so keep "
       "it up to date."),
    _t("your-account-privacy", "How Northline protects your account information", "Other",
       "Call records, usage and billing details are protected information. Support confirms "
       "identity with the account PIN before discussing an account. Only the account owner "
       "and authorized users can get account details."),
)  # fmt: skip
