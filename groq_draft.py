"""
connectd - groq message drafting
reads soul from file, uses as guideline for llm to personalize
"""

import os
import json
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# load soul from file (guideline, not script)
SOUL_PATH = os.getenv("SOUL_PATH", "/app/soul.txt")
def load_soul():
    try:
        with open(SOUL_PATH, 'r') as f:
            return f.read().strip()
    except:
        return None

SIGNATURE_HTML = """
<div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #333;">
  <div style="margin-bottom: 12px;">
    <a href="https://github.com/sudoxnym/connectd" style="color: #8b5cf6; text-decoration: none; font-size: 14px;">github.com/sudoxnym/connectd</a>
    <span style="color: #666; font-size: 12px; margin-left: 8px;">(main repo)</span>
  </div>
  <div style="display: flex; gap: 16px; align-items: center;">
    <a href="https://github.com/connectd-daemon" title="GitHub" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
    </a>
    <a href="https://mastodon.sudoxreboot.com/@connectd" title="Mastodon" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M23.268 5.313c-.35-2.578-2.617-4.61-5.304-5.004C17.51.242 15.792 0 11.813 0h-.03c-3.98 0-4.835.242-5.288.309C3.882.692 1.496 2.518.917 5.127.64 6.412.61 7.837.661 9.143c.074 1.874.088 3.745.26 5.611.118 1.24.325 2.47.62 3.68.55 2.237 2.777 4.098 4.96 4.857 2.336.792 4.849.923 7.256.38.265-.061.527-.132.786-.213.585-.184 1.27-.39 1.774-.753a.057.057 0 0 0 .023-.043v-1.809a.052.052 0 0 0-.02-.041.053.053 0 0 0-.046-.01 20.282 20.282 0 0 1-4.709.545c-2.73 0-3.463-1.284-3.674-1.818a5.593 5.593 0 0 1-.319-1.433.053.053 0 0 1 .066-.054c1.517.363 3.072.546 4.632.546.376 0 .75 0 1.125-.01 1.57-.044 3.224-.124 4.768-.422.038-.008.077-.015.11-.024 2.435-.464 4.753-1.92 4.989-5.604.008-.145.03-1.52.03-1.67.002-.512.167-3.63-.024-5.545zm-3.748 9.195h-2.561V8.29c0-1.309-.55-1.976-1.67-1.976-1.23 0-1.846.79-1.846 2.35v3.403h-2.546V8.663c0-1.56-.617-2.35-1.848-2.35-1.112 0-1.668.668-1.67 1.977v6.218H4.822V8.102c0-1.31.337-2.35 1.011-3.12.696-.77 1.608-1.164 2.74-1.164 1.311 0 2.302.5 2.962 1.498l.638 1.06.638-1.06c.66-.999 1.65-1.498 2.96-1.498 1.13 0 2.043.395 2.74 1.164.675.77 1.012 1.81 1.012 3.12z"/></svg>
    </a>
    <a href="https://bsky.app/profile/connectd.bsky.social" title="Bluesky" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M5.202 2.857C7.954 4.922 10.913 9.11 12 11.358c1.087-2.247 4.046-6.436 6.798-8.501C20.783 1.366 24 .213 24 3.883c0 .732-.42 6.156-.667 7.037-.856 3.061-3.978 3.842-6.755 3.37 4.854.826 6.089 3.562 3.422 6.299-5.065 5.196-7.28-1.304-7.847-2.97-.104-.305-.152-.448-.153-.327 0-.121-.05.022-.153.327-.568 1.666-2.782 8.166-7.847 2.97-2.667-2.737-1.432-5.473 3.422-6.3-2.777.473-5.899-.308-6.755-3.369C.42 10.04 0 4.615 0 3.883c0-3.67 3.217-2.517 5.202-1.026"/></svg>
    </a>
    <a href="https://lemmy.sudoxreboot.com/c/connectd" title="Lemmy" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.9595 4.2228a3.9132 3.9132 0 0 0-.332.019c-.8781.1012-1.67.5699-2.155 1.3862-.475.8-.5922 1.6809-.35 2.4971.2421.8162.8297 1.5575 1.6982 2.1449.0053.0035.0106.0076.0163.0114.746.4498 1.492.7431 2.2877.8994-.02.3318-.0272.6689-.006 1.0181.0634 1.0432.4368 2.0006.996 2.8492l-2.0061.8189a.4163.4163 0 0 0-.2276.2239.416.416 0 0 0 .0879.455.415.415 0 0 0 .2941.1231.4156.4156 0 0 0 .1595-.0312l2.2093-.9035c.408.4859.8695.9315 1.3723 1.318.0196.0151.0407.0264.0603.0423l-1.2918 1.7103a.416.416 0 0 0 .664.501l1.314-1.7385c.7185.4548 1.4782.7927 2.2294 1.0242.3833.7209 1.1379 1.1871 2.0202 1.1871.8907 0 1.6442-.501 2.0242-1.2072.744-.2347 1.4959-.5729 2.2073-1.0262l1.332 1.7606a.4157.4157 0 0 0 .7439-.1936.4165.4165 0 0 0-.0799-.3074l-1.3099-1.7345c.0083-.0075.0178-.0113.0261-.0188.4968-.3803.9549-.8175 1.3622-1.2939l2.155.8794a.4156.4156 0 0 0 .5412-.2276.4151.4151 0 0 0-.2273-.5432l-1.9438-.7928c.577-.8538.9697-1.8183 1.0504-2.8693.0268-.3507.0242-.6914.0079-1.0262.7905-.1572 1.5321-.4502 2.2737-.8974.0053-.0033.011-.0076.0163-.0113.8684-.5874 1.456-1.3287 1.6982-2.145.2421-.8161.125-1.697-.3501-2.497-.4849-.8163-1.2768-1.2852-2.155-1.3863a3.2175 3.2175 0 0 0-.332-.0189c-.7852-.0151-1.6231.229-2.4286.6942-.5926.342-1.1252.867-1.5433 1.4387-1.1699-.6703-2.6923-1.0476-4.5635-1.0785a15.5768 15.5768 0 0 0-.5111 0c-2.085.034-3.7537.43-5.0142 1.1449-.0033-.0038-.0045-.0114-.008-.0152-.4233-.5916-.973-1.1365-1.5835-1.489-.8055-.465-1.6434-.7083-2.4286-.6941Zm.2858.7365c.5568.042 1.1696.2358 1.7787.5875.485.28.9757.7554 1.346 1.2696a5.6875 5.6875 0 0 0-.4969.4085c-.9201.8516-1.4615 1.9597-1.668 3.2335-.6809-.1402-1.3183-.3945-1.984-.7948-.7553-.5128-1.2159-1.1225-1.4004-1.7445-.1851-.624-.1074-1.2712.2776-1.9196.3743-.63.9275-.9534 1.6118-1.0322a2.796 2.796 0 0 1 .5352-.0076Zm17.5094 0a2.797 2.797 0 0 1 .5353.0075c.6842.0786 1.2374.4021 1.6117 1.0322.385.6484.4627 1.2957.2776 1.9196-.1845.622-.645 1.2317-1.4004 1.7445-.6578.3955-1.2881.6472-1.9598.7888-.1942-1.2968-.7375-2.4338-1.666-3.302a5.5639 5.5639 0 0 0-.4709-.3923c.3645-.49.8287-.9428 1.2938-1.2113.6091-.3515 1.2219-.5454 1.7787-.5875ZM12.006 6.0036a14.832 14.832 0 0 1 .487 0c2.3901.0393 4.0848.67 5.1631 1.678 1.1501 1.0754 1.6423 2.6006 1.499 4.467-.1311 1.7079-1.2203 3.2281-2.652 4.324-.694.5313-1.4626.9354-2.2254 1.2294.0031-.0453.014-.0888.014-.1349.0029-1.1964-.9313-2.2133-2.2918-2.2133-1.3606 0-2.3222 1.0154-2.2918 2.2213.0013.0507.014.0972.0181.1471-.781-.2933-1.5696-.7013-2.2777-1.2456-1.4239-1.0945-2.4997-2.6129-2.6037-4.322-.1129-1.8567.3778-3.3382 1.5212-4.3965C7.5094 6.7 9.352 6.047 12.006 6.0036Zm-3.6419 6.8291c-.6053 0-1.0966.4903-1.0966 1.0966 0 .6063.4913 1.0986 1.0966 1.0986s1.0966-.4923 1.0966-1.0986c0-.6063-.4913-1.0966-1.0966-1.0966zm7.2819.0113c-.5998 0-1.0866.4859-1.0866 1.0866s.4868 1.0885 1.0866 1.0885c.5997 0 1.0865-.4878 1.0865-1.0885s-.4868-1.0866-1.0865-1.0866zM12 16.0835c1.0237 0 1.5654.638 1.5634 1.4829-.0018.7849-.6723 1.485-1.5634 1.485-.9167 0-1.54-.5629-1.5634-1.493-.0212-.8347.5397-1.4749 1.5634-1.4749Z"/></svg>
    </a>
    <a href="https://discord.gg/connectd" title="Discord" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.3698a19.7913 19.7913 0 00-4.8851-1.5152.0741.0741 0 00-.0785.0371c-.211.3753-.4447.8648-.6083 1.2495-1.8447-.2762-3.68-.2762-5.4868 0-.1636-.3933-.4058-.8742-.6177-1.2495a.077.077 0 00-.0785-.037 19.7363 19.7363 0 00-4.8852 1.515.0699.0699 0 00-.0321.0277C.5334 9.0458-.319 13.5799.0992 18.0578a.0824.0824 0 00.0312.0561c2.0528 1.5076 4.0413 2.4228 5.9929 3.0294a.0777.0777 0 00.0842-.0276c.4616-.6304.8731-1.2952 1.226-1.9942a.076.076 0 00-.0416-.1057c-.6528-.2476-1.2743-.5495-1.8722-.8923a.077.077 0 01-.0076-.1277c.1258-.0943.2517-.1923.3718-.2914a.0743.0743 0 01.0776-.0105c3.9278 1.7933 8.18 1.7933 12.0614 0a.0739.0739 0 01.0785.0095c.1202.099.246.1981.3728.2924a.077.077 0 01-.0066.1276 12.2986 12.2986 0 01-1.873.8914.0766.0766 0 00-.0407.1067c.3604.698.7719 1.3628 1.225 1.9932a.076.076 0 00.0842.0286c1.961-.6067 3.9495-1.5219 6.0023-3.0294a.077.077 0 00.0313-.0552c.5004-5.177-.8382-9.6739-3.5485-13.6604a.061.061 0 00-.0312-.0286zM8.02 15.3312c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9555-2.4189 2.157-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.9555 2.4189-2.1569 2.4189zm7.9748 0c-1.1825 0-2.1569-1.0857-2.1569-2.419 0-1.3332.9554-2.4189 2.1569-2.4189 1.2108 0 2.1757 1.0952 2.1568 2.419 0 1.3332-.946 2.4189-2.1568 2.4189Z"/></svg>
    </a>
    <a href="https://matrix.to/#/@connectd:sudoxreboot.com" title="Matrix" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M.632.55v22.9H2.28V24H0V0h2.28v.55zm7.043 7.26v1.157h.033c.309-.443.683-.784 1.117-1.024.433-.245.936-.365 1.5-.365.54 0 1.033.107 1.481.314.448.208.785.582 1.02 1.108.254-.374.6-.706 1.034-.992.434-.287.95-.43 1.546-.43.453 0 .872.056 1.26.167.388.11.716.286.993.53.276.245.489.559.646.951.152.392.23.863.23 1.417v5.728h-2.349V11.52c0-.286-.01-.559-.032-.812a1.755 1.755 0 0 0-.18-.66 1.106 1.106 0 0 0-.438-.448c-.194-.11-.457-.166-.785-.166-.332 0-.6.064-.803.189a1.38 1.38 0 0 0-.48.499 1.946 1.946 0 0 0-.231.696 5.56 5.56 0 0 0-.06.785v4.768h-2.35v-4.8c0-.254-.004-.503-.018-.752a2.074 2.074 0 0 0-.143-.688 1.052 1.052 0 0 0-.415-.503c-.194-.125-.476-.19-.854-.19-.111 0-.259.024-.439.074-.18.051-.36.143-.53.282-.171.138-.319.337-.439.595-.12.259-.18.6-.18 1.02v4.966H5.46V7.81zm15.693 15.64V.55H21.72V0H24v24h-2.28v-.55z"/></svg>
    </a>
    <a href="https://reddit.com/r/connectd" title="Reddit" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.373 0 0 5.373 0 12c0 3.314 1.343 6.314 3.515 8.485l-2.286 2.286C.775 23.225 1.097 24 1.738 24H12c6.627 0 12-5.373 12-12S18.627 0 12 0Zm4.388 3.199c1.104 0 1.999.895 1.999 1.999 0 1.105-.895 2-1.999 2-.946 0-1.739-.657-1.947-1.539v.002c-1.147.162-2.032 1.15-2.032 2.341v.007c1.776.067 3.4.567 4.686 1.363.473-.363 1.064-.58 1.707-.58 1.547 0 2.802 1.254 2.802 2.802 0 1.117-.655 2.081-1.601 2.531-.088 3.256-3.637 5.876-7.997 5.876-4.361 0-7.905-2.617-7.998-5.87-.954-.447-1.614-1.415-1.614-2.538 0-1.548 1.255-2.802 2.803-2.802.645 0 1.239.218 1.712.585 1.275-.79 2.881-1.291 4.64-1.365v-.01c0-1.663 1.263-3.034 2.88-3.207.188-.911.993-1.595 1.959-1.595Zm-8.085 8.376c-.784 0-1.459.78-1.506 1.797-.047 1.016.64 1.429 1.426 1.429.786 0 1.371-.369 1.418-1.385.047-1.017-.553-1.841-1.338-1.841Zm7.406 0c-.786 0-1.385.824-1.338 1.841.047 1.017.634 1.385 1.418 1.385.785 0 1.473-.413 1.426-1.429-.046-1.017-.721-1.797-1.506-1.797Zm-3.703 4.013c-.974 0-1.907.048-2.77.135-.147.015-.241.168-.183.305.483 1.154 1.622 1.964 2.953 1.964 1.33 0 2.47-.81 2.953-1.964.057-.137-.037-.29-.184-.305-.863-.087-1.795-.135-2.769-.135Z"/></svg>
    </a>
    <a href="mailto:connectd@sudoxreboot.com" title="Email" style="color: #888; text-decoration: none;">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M1.5 8.67v8.58a3 3 0 003 3h15a3 3 0 003-3V8.67l-8.928 5.493a3 3 0 01-3.144 0L1.5 8.67z"/><path d="M22.5 6.908V6.75a3 3 0 00-3-3h-15a3 3 0 00-3 3v.158l9.714 5.978a1.5 1.5 0 001.572 0L22.5 6.908z"/></svg>
    </a>
  </div>
</div>
"""

SIGNATURE_PLAINTEXT = """
---
github.com/sudoxnym/connectd (main repo)

github: github.com/connectd-daemon
mastodon: @connectd@mastodon.sudoxreboot.com
bluesky: connectd.bsky.social
lemmy: lemmy.sudoxreboot.com/c/connectd
discord: discord.gg/connectd
matrix: @connectd:sudoxreboot.com
reddit: reddit.com/r/connectd
email: connectd@sudoxreboot.com
"""


def draft_intro_with_llm(match_data: dict, recipient: str = 'a', dry_run: bool = True):
    """
    draft an intro message using groq llm.
    
    args:
        match_data: dict with human_a, human_b, overlap_score, overlap_reasons
        recipient: 'a' or 'b' - who receives the message
        dry_run: if True, preview mode
    
    returns:
        tuple (result_dict, error_string)
        result_dict has: subject, draft_html, draft_plain
    """
    if not client:
        return None, "GROQ_API_KEY not set"
    
    try:
        human_a = match_data.get('human_a', {})
        human_b = match_data.get('human_b', {})
        reasons = match_data.get('overlap_reasons', [])
        
        # recipient gets the message, about_person is who we're introducing them to
        if recipient == 'a':
            to_person = human_a
            about_person = human_b
        else:
            to_person = human_b
            about_person = human_a
        
        to_name = to_person.get('username', 'friend')
        about_name = about_person.get('username', 'someone')
        about_bio = about_person.get('extra', {}).get('bio', '')
        
        # extract contact info for about_person
        about_extra = about_person.get('extra', {})
        if isinstance(about_extra, str):
            import json as _json
            about_extra = _json.loads(about_extra) if about_extra else {}
        about_contact = about_person.get('contact', {})
        if isinstance(about_contact, str):
            about_contact = _json.loads(about_contact) if about_contact else {}
        
        # build contact link for about_person
        about_platform = about_person.get('platform', '')
        about_username = about_person.get('username', '')
        contact_link = None
        if about_platform == 'mastodon' and about_username:
            if '@' in about_username:
                parts = about_username.split('@')
                if len(parts) >= 2:
                    contact_link = f"https://{parts[1]}/@{parts[0]}"
        elif about_platform == 'github' and about_username:
            contact_link = f"https://github.com/{about_username}"
        elif about_extra.get('mastodon') or about_contact.get('mastodon'):
            handle = about_extra.get('mastodon') or about_contact.get('mastodon')
            if '@' in handle:
                parts = handle.lstrip('@').split('@')
                if len(parts) >= 2:
                    contact_link = f"https://{parts[1]}/@{parts[0]}"
        elif about_extra.get('github') or about_contact.get('github'):
            contact_link = f"https://github.com/{about_extra.get('github') or about_contact.get('github')}"
        elif about_extra.get('email'):
            contact_link = about_extra['email']
        elif about_contact.get('email'):
            contact_link = about_contact['email']
        elif about_extra.get('website'):
            contact_link = about_extra['website']
        elif about_extra.get('external_links', {}).get('website'):
            contact_link = about_extra['external_links']['website']
        elif about_extra.get('extra', {}).get('website'):
            contact_link = about_extra['extra']['website']
        elif about_platform == 'reddit' and about_username:
            contact_link = f"reddit.com/u/{about_username}"
        
        if not contact_link:
            contact_link = f"github.com/{about_username}" if about_username else "reach out via connectd"
        
        # skip if no real contact method (just reddit or generic)
        if contact_link.startswith('reddit.com') or contact_link == "reach out via connectd" or 'stackblitz' in contact_link:
            return None, f"no real contact info for {about_name} - skipping draft"
        
        # format the shared factors naturally
        if reasons:
            factor = ', '.join(reasons[:3]) if len(reasons) > 1 else reasons[0]
        else:
            factor = "shared values and interests"
        
        # load soul as guideline
        soul = load_soul()
        if not soul:
            return None, "could not load soul file"
        
        # build the prompt - soul is GUIDELINE not script
        prompt = f"""you are connectd, a daemon that finds isolated builders and connects them.

write a personal message TO {to_name} telling them about {about_name}.

here is the soul/spirit of what connectd is about - use this as a GUIDELINE for tone and message, NOT as a script to copy verbatim:

---
{soul}
---

key facts for this message:
- recipient: {to_name}
- introducing them to: {about_name}
- their shared interests/values: {factor}
- about {about_name}: {about_bio if about_bio else 'a builder like you'}
- HOW TO REACH {about_name}: {contact_link}

RULES:
1. say their name ONCE at start, then use "you" 
2. MUST include how to reach {about_name}: {contact_link}
3. lowercase, raw, emotional - follow the soul
4. end with the contact link

return ONLY the message body. signature is added separately."""

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=1200
        )
        
        body = response.choices[0].message.content.strip()
        
        # generate subject
        subject_prompt = f"""generate a short, lowercase email subject for a message to {to_name} about connecting them with {about_name} over their shared interest in {factor}.

no corporate speak. no clickbait. raw and real.
examples:
- "found you, {to_name}"
- "you're not alone"
- "a door just opened"
- "{to_name}, there's someone you should meet"

return ONLY the subject line."""

        subject_response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": subject_prompt}],
            temperature=0.9,
            max_tokens=50
        )
        
        subject = subject_response.choices[0].message.content.strip().strip('"').strip("'")
        
        # format html
        draft_html = f"<div style='font-family: monospace; white-space: pre-wrap; color: #e0e0e0; background: #1a1a1a; padding: 20px;'>{body}</div>{SIGNATURE_HTML}"
        draft_plain = body + SIGNATURE_PLAINTEXT
        
        return {
            'subject': subject,
            'draft_html': draft_html,
            'draft_plain': draft_plain
        }, None
        
    except Exception as e:
        return None, str(e)


# for backwards compat with old code
def draft_message(person: dict, factor: str, platform: str = "email") -> dict:
    """legacy function - wraps new api"""
    match_data = {
        'human_a': {'username': 'recipient'},
        'human_b': person,
        'overlap_reasons': [factor]
    }
    result, error = draft_intro_with_llm(match_data, recipient='a')
    if error:
        raise ValueError(error)
    return {
        'subject': result['subject'],
        'body_html': result['draft_html'],
        'body_plain': result['draft_plain']
    }


if __name__ == "__main__":
    # test
    test_data = {
        'human_a': {'username': 'sudoxnym', 'extra': {'bio': 'building intentional communities'}},
        'human_b': {'username': 'testuser', 'extra': {'bio': 'home assistant enthusiast'}},
        'overlap_reasons': ['home-assistant', 'open source', 'community building']
    }
    result, error = draft_intro_with_llm(test_data, recipient='a')
    if error:
        print(f"error: {error}")
    else:
        print(f"subject: {result['subject']}")
        print(f"\nbody:\n{result['draft_plain']}")

# contact method ranking - USAGE BASED
# we rank by where the person is MOST ACTIVE, not by our preference

def determine_contact_method(human):
    """
    determine ALL available contact methods, ranked by USER'S ACTIVITY.
    
    looks at activity metrics to decide where they're most engaged.
    returns: (best_method, best_info, fallbacks)
    where fallbacks is a list of (method, info) tuples in activity order
    """
    import json
    
    extra = human.get('extra', {})
    contact = human.get('contact', {})
    
    if isinstance(extra, str):
        extra = json.loads(extra) if extra else {}
    if isinstance(contact, str):
        contact = json.loads(contact) if contact else {}
    
    nested_extra = extra.get('extra', {})
    platform = human.get('platform', '')
    
    available = []
    
    # === ACTIVITY SCORING ===
    # each method gets scored by how active the user is there
    
    # EMAIL - always medium priority (we cant measure activity)
    email = extra.get('email') or contact.get('email') or nested_extra.get('email')
    if email and '@' in str(email):
        available.append(('email', email, 50))  # baseline score
    
    # MASTODON - score by post count / followers
    mastodon = extra.get('mastodon') or contact.get('mastodon') or nested_extra.get('mastodon')
    if mastodon:
        masto_activity = extra.get('mastodon_posts', 0) or extra.get('statuses_count', 0)
        masto_score = min(100, 30 + (masto_activity // 10))  # 30 base + 1 per 10 posts
        available.append(('mastodon', mastodon, masto_score))
    
    # if they CAME FROM mastodon, thats their primary
    if platform == 'mastodon':
        handle = f"@{human.get('username')}"
        instance = human.get('instance') or extra.get('instance') or ''
        if instance:
            handle = f"@{human.get('username')}@{instance}"
        activity = extra.get('statuses_count', 0) or extra.get('activity_count', 0)
        score = min(100, 50 + (activity // 5))  # higher base since its their home
        # dont dupe
        if not any(a[0] == 'mastodon' for a in available):
            available.append(('mastodon', handle, score))
        else:
            # update score if this is higher
            for i, (m, info, s) in enumerate(available):
                if m == 'mastodon' and score > s:
                    available[i] = ('mastodon', handle, score)
    
    # MATRIX - score by presence (binary for now)
    matrix = extra.get('matrix') or contact.get('matrix') or nested_extra.get('matrix')
    if matrix and ':' in str(matrix):
        available.append(('matrix', matrix, 40))
    
    # BLUESKY - score by followers/posts if available
    bluesky = extra.get('bluesky') or contact.get('bluesky') or nested_extra.get('bluesky')
    if bluesky:
        bsky_activity = extra.get('bluesky_posts', 0)
        bsky_score = min(100, 25 + (bsky_activity // 10))
        available.append(('bluesky', bluesky, bsky_score))
    
    # LEMMY - score by activity
    lemmy = extra.get('lemmy') or contact.get('lemmy') or nested_extra.get('lemmy')
    if lemmy:
        lemmy_activity = extra.get('lemmy_posts', 0) or extra.get('lemmy_comments', 0)
        lemmy_score = min(100, 30 + lemmy_activity)
        available.append(('lemmy', lemmy, lemmy_score))
    
    if platform == 'lemmy':
        handle = human.get('username')
        activity = extra.get('activity_count', 0)
        score = min(100, 50 + activity)
        if not any(a[0] == 'lemmy' for a in available):
            available.append(('lemmy', handle, score))
    
    # DISCORD - lower priority (hard to DM)
    discord = extra.get('discord') or contact.get('discord') or nested_extra.get('discord')
    if discord:
        available.append(('discord', discord, 20))
    
    # GITHUB ISSUE - for github users, score by repo activity
    if platform == 'github':
        top_repos = extra.get('top_repos', [])
        if top_repos:
            repo = top_repos[0] if isinstance(top_repos[0], str) else top_repos[0].get('name', '')
            stars = extra.get('total_stars', 0)
            repos_count = extra.get('repos_count', 0)
            # active github user = higher issue score
            gh_score = min(60, 20 + (stars // 100) + (repos_count // 5))
            if repo:
                available.append(('github_issue', f"{human.get('username')}/{repo}", gh_score))

    # FORGE ISSUE - for self-hosted git users (gitea/forgejo/gitlab/sourcehut/codeberg)
    # these are HIGH SIGNAL users - they actually selfhost
    if platform and ':' in platform:
        platform_type, instance = platform.split(':', 1)
        if platform_type in ('gitea', 'forgejo', 'gogs', 'gitlab', 'sourcehut'):
            repos = extra.get('repos', [])
            if repos:
                repo = repos[0] if isinstance(repos[0], str) else repos[0].get('name', '')
                instance_url = extra.get('instance_url', '')
                if repo and instance_url:
                    # forge users get higher priority than github (they selfhost!)
                    forge_score = 55  # higher than github_issue (50)
                    available.append(('forge_issue', {
                        'platform_type': platform_type,
                        'instance': instance,
                        'instance_url': instance_url,
                        'owner': human.get('username'),
                        'repo': repo
                    }, forge_score))
    
    # REDDIT - discovered people, use their other links
    if platform == 'reddit':
        reddit_activity = extra.get('reddit_activity', 0) or extra.get('activity_count', 0)
        # reddit users we reach via their external links (email, mastodon, etc)
        # boost their other methods if reddit is their main platform
        for i, (m, info, score) in enumerate(available):
            if m in ('email', 'mastodon', 'matrix', 'bluesky'):
                # boost score for reddit-discovered users' external contacts
                boost = min(30, reddit_activity // 3)
                available[i] = (m, info, score + boost)
    
    # sort by activity score (highest first)
    available.sort(key=lambda x: x[2], reverse=True)
    
    if not available:
        return 'manual', None, []
    
    best = available[0]
    fallbacks = [(m, i) for m, i, p in available[1:]]
    
    return best[0], best[1], fallbacks


def get_ranked_contact_methods(human):
    """
    get all contact methods for a human, ranked by their activity.
    """
    method, info, fallbacks = determine_contact_method(human)
    if method == 'manual':
        return []
    return [(method, info)] + fallbacks
