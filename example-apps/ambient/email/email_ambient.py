import imaplib
import logging
import time
import base64 
from email import message_from_bytes
from email.message import Message
from email.header import decode_header, make_header
from email.utils import parseaddr, getaddresses
from typing import List, Optional, Tuple
from truffle.app.background_feed_pb2 import FeedCard

from gourmet.ambient import run_ambient, AmbientContext
logger = logging.getLogger("email")
logger.setLevel(logging.DEBUG)

from dataclasses import dataclass

@dataclass
class EmailConfig:
    imap_server: str
    email_address : str
    email_password: str
    imap_port: int = 993
    imap_ssl: bool = True
    mailbox: str = "inbox"

    @staticmethod
    def from_env() -> 'EmailConfig':
        import os
        imap_server = os.getenv("IMAP_SERVER", "imap.gmail.com")
        email_address = os.getenv("EMAIL_ADDRESS", "")
        email_password = os.getenv("EMAIL_PASSWORD", "")
        imap_port = int(os.getenv("IMAP_PORT", "993"))
        imap_ssl = os.getenv("IMAP_SSL", "1") == "1"
        mailbox = os.getenv("MAILBOX", "inbox")
        cfg =  EmailConfig(
            imap_server=imap_server,
            email_address=email_address,
            email_password=email_password,
            imap_port=imap_port,
            imap_ssl=imap_ssl,
            mailbox=mailbox
        )
        if not all([imap_server, email_address, email_password]):
            logger.error("EmailConfig.from_env: Missing required configuration: ", str(cfg))
            raise ValueError("Missing required email configuration in environment variables")
        return cfg
    
    def is_gmail(self) -> bool:
        return self.imap_server.lower() == "imap.gmail.com"
    

email_config = EmailConfig.from_env()

LAST_SEEN_UID: Optional[int] = None

def connect_to_email(cfg : EmailConfig) -> imaplib.IMAP4_SSL:
    try:
        mail = imaplib.IMAP4_SSL(cfg.imap_server, cfg.imap_port)
        mail.login(cfg.email_address, cfg.email_password)
        return mail
    except Exception as e:
        safe_pwd = cfg.email_password[:2] + "***" + cfg.email_password[-2:] # logs are private to user device anyways 
        logging.error(f"Connection to {cfg.imap_server} as {cfg.email_address}:{safe_pwd} failed")
        logging.error(str(e))
        raise



def _init_last_uid(mail: imaplib.IMAP4_SSL) -> int:
    status, data = mail.uid("search", None, "ALL") # type: ignore
    if status != "OK":
        raise RuntimeError("Failed to search mailbox to initialize last UID")
    if not data or not data[0]:
        return 0
    uids = data[0].split()
    return int(uids[-1])


def decode_mime_header(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        dh = decode_header(value)
        # make_header handles joining parts + charset decoding
        return str(make_header(dh))
    except Exception:
        return value
def parse_single_address(h: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not h:
        return None, None
    decoded = decode_mime_header(h) or ""
    name, addr = parseaddr(decoded)
    name = name or None
    addr = addr or None
    return name, addr


def fetch_new_emails(
    mail: imaplib.IMAP4_SSL,
    last_seen_uid: int | None = None,
) -> Tuple[List[Message], Optional[int]]:
    global email_config
    try:
        status, _ = mail.select(email_config.mailbox)
        if status != "OK":
            raise RuntimeError(f"Failed to select mailbox {email_config.mailbox}")

        if last_seen_uid is None:
            last_seen_uid = _init_last_uid(mail)
            logger.debug("Initialized last_seen_uid to %s", last_seen_uid)

        start_uid = (last_seen_uid or 0) + 1
        search_criteria = f"UID {start_uid}:*"

        status, data = mail.uid("search", None, search_criteria)  # type: ignore
        if status != "OK":
            logger.error("UID SEARCH failed with %r", search_criteria)
            return [], last_seen_uid

        if not data or not data[0]:
            logger.debug("No new messages since UID %s", last_seen_uid)
            return [], last_seen_uid

        uids = data[0].split()
        messages: List[Message] = []
        max_uid = last_seen_uid or 0

        for uid in uids:
            uid_int = int(uid)
            if last_seen_uid and uid_int == last_seen_uid:
                continue
            

            # one fetch: body (no \Seen) + X-GM-MSGID
            # hopefully other IMAP servers just ignore X-GM-MSGID
            status, msg_data = mail.uid("fetch", uid, "(BODY.PEEK[] X-GM-MSGID)")
            if status != "OK" or not msg_data:
                logger.error("Failed to fetch message UID %s", uid.decode())
                continue

            meta_bytes = None
            raw_bytes = None
            for item in msg_data:
                if isinstance(item, tuple):
                    meta_bytes, raw_bytes = item
                    break

            if meta_bytes is None or raw_bytes is None:
                logger.error("Unexpected fetch response for UID %s: %r", uid.decode(), msg_data)
                continue

            meta = meta_bytes.decode("utf-8", errors="ignore")
            gm_msgid: Optional[str] = None
            if "X-GM-MSGID" in meta:
                after = meta.split("X-GM-MSGID", 1)[1].strip()
                gm_msgid = after.split()[0].rstrip(")")

            msg = message_from_bytes(raw_bytes)
            msg.add_header("UID", str(uid_int))
            if gm_msgid and email_config.is_gmail():
                msg.add_header(
                    "GMAIL_URL", # this assumes inbox 0, not great but whatever
                    f"https://mail.google.com/mail/u/0/#all/{int(gm_msgid):x}",
                )

            messages.append(msg)
            if uid_int > max_uid:
                max_uid = uid_int

        if max_uid > (last_seen_uid or 0):
            last_seen_uid = max_uid

        logger.info(
            "Fetched %d new messages, last_seen_uid=%s",
            len(messages),
            last_seen_uid,
        )
        return messages, last_seen_uid
    except Exception as e:
        logger.error(f"Error fetching new emails: {str(e)}", exc_info=True)
        return [], last_seen_uid

def _decode_part(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace") # type: ignore
    except LookupError:
        return payload.decode("utf-8", errors="replace") # type: ignore


def extract_preferred_body(msg: Message) -> Tuple[Optional[str],Optional[str], bool]:
    text_body: Optional[str] = None
    html_body: Optional[str] = None

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            if "attachment" in disp:
                continue

            if ctype == "text/plain":
                decoded = _decode_part(part).strip()
                if decoded:
                    text_body = decoded if text_body is None else (text_body + "\n" + decoded)
            elif ctype == "text/html":
                decoded = _decode_part(part).strip()
                if decoded:
                    html_body = decoded if html_body is None else (html_body + "\n" + decoded)
    else:
        ctype = msg.get_content_type()
        decoded = _decode_part(msg).strip()
        if ctype == "text/plain":
            text_body = decoded or None
        elif ctype == "text/html":
            html_body = decoded or None
    return text_body, html_body, True if html_body is not None else False
   


def email_ambient(ctx: AmbientContext):
    global LAST_SEEN_UID
    global email_config
    mail = connect_to_email(email_config)
    try:
        messages, new_uid = fetch_new_emails(mail, LAST_SEEN_UID)
        logger.info(f"Fetched {len(messages)} new emails, new last seen UID: {new_uid}")
        LAST_SEEN_UID = new_uid
        if not messages or len(messages) == 0:
            return

        for msg in messages:
            body, html_body, is_html = extract_preferred_body(msg)
           
            uid = msg.get("UID")
            gmail_url = msg.get("GMAIL_URL")
            subject = decode_mime_header(msg["Subject"])
            sender = msg["From"]
            name, sender_addr = parse_single_address(sender)
            if not name or not sender_addr:
                name = ""
                sender_addr = sender_addr or ""
                if len(sender_addr) == 0:
                    sender_addr = sender

            recv = msg["To"]
            logger.info(f"Email UID: {uid}, From: {name} {sender_addr}, To: {recv}, Subject: {subject}, Is HTML: {is_html}, Body {len(body or "")} GMAIL_URL: {gmail_url} ")
            if is_html and html_body is not None:
                try:
                    # just use trafilatura if we can
                    import trafilatura
                    extracted = trafilatura.extract(html_body, output_format="markdown", include_tables=True, include_links=True, include_images=True, deduplicate=True, favor_precision=True)
                    if extracted:
                        body = extracted.strip()
                    logger.info("Extracted text from HTML email using trafilatura.")
                except ImportError:
                    logger.warning("trafilatura not installed, skipping HTML to text conversion")
                    body = html_body.strip()
                except Exception as e:
                    logger.error(f"Error during HTML to text conversion: {str(e)}", exc_info=True)
                    body = html_body.strip()
            elif body is not None and len(body.strip()) == 0:
                body = "[No content]"

            if subject is None or len(subject.strip()) == 0:
                subject = "(No Subject)"

            

            card = FeedCard()
            card.title = subject
            rich_sender = f"[{name}](mail-to:{sender_addr})" if name else sender_addr

            card.body = f"{rich_sender}\n{body}"
            if gmail_url:
                card.source_uri = gmail_url
            ctx.bg.add_feed_card(card)
    except Exception as e:
        logger.error(f"Error in email_ambient: {str(e)}", exc_info=True)
    finally:
        try:
            mail.close()
        except Exception:
            pass
        try:
            mail.logout()
        except Exception:
            pass
    time.sleep(0.2) # sanity check everything closed ok 

def verify() -> int:
    global LAST_SEEN_UID
    global email_config
    mail : imaplib.IMAP4_SSL | None = None
    try: 
        mail = connect_to_email(email_config)
        mail.select(email_config.mailbox)
        logger.info(f"Connected to IMAP server {email_config.imap_server} as {email_config.email_address}, mailbox {email_config.mailbox}")
        logger.info("email is properly configured!")
        return 0
    except Exception as e:
        logger.error(f"Failed to connect to email server: {str(e)}", exc_info=True)
        return 1
    finally:
        if mail is not None:
            try:
                mail.close()
            except Exception:
                pass
            try:
                mail.logout()
            except Exception:
                pass

if __name__ == "__main__":
    import sys 
    if sys.argv and len(sys.argv) > 1 and  "verify" in sys.argv[1].lower():
        logger.info("Running Email Ambient App VERIFY mode")
        ec = verify()
        logger.info(f"Email Ambient App VERIFY exited with code {ec}")
        sys.exit(ec)
    else:
        run_ambient(email_ambient)