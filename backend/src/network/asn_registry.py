"""ASN-to-Name Registry — 200+ common Autonomous System Numbers mapped to names.

Includes major cloud providers, CDNs, ISPs, transit providers, IXPs,
hosting companies, and enterprise networks worldwide.
"""
from __future__ import annotations

ASN_REGISTRY: dict[int, dict] = {
    # ═══════════════════════════════════════════════════════════════
    # Major Cloud / Hyperscaler
    # ═══════════════════════════════════════════════════════════════
    13335: {"name": "Cloudflare", "country": "US"},
    15169: {"name": "Google", "country": "US"},
    16509: {"name": "Amazon", "country": "US"},
    32934: {"name": "Facebook", "country": "US"},
    8075: {"name": "Microsoft", "country": "US"},
    14618: {"name": "Amazon (AWS)", "country": "US"},
    16591: {"name": "Google Cloud", "country": "US"},
    36459: {"name": "GitHub", "country": "US"},
    54113: {"name": "Fastly", "country": "US"},
    20940: {"name": "Akamai", "country": "US"},
    16625: {"name": "Akamai", "country": "US"},
    32787: {"name": "Akamai (Prolexic)", "country": "US"},
    13414: {"name": "Twitter", "country": "US"},
    2906: {"name": "Netflix", "country": "US"},
    40027: {"name": "Apple", "country": "US"},
    714: {"name": "Apple", "country": "US"},
    36351: {"name": "SoftLayer (IBM Cloud)", "country": "US"},
    19527: {"name": "Google (YouTube)", "country": "US"},
    396982: {"name": "Google Cloud", "country": "US"},
    36492: {"name": "Google", "country": "US"},
    395973: {"name": "Google", "country": "US"},
    63179: {"name": "Oracle Cloud", "country": "US"},
    31898: {"name": "Oracle", "country": "US"},
    4808: {"name": "Alibaba Cloud", "country": "CN"},
    45102: {"name": "Alibaba Cloud", "country": "CN"},
    37963: {"name": "Alibaba (Hangzhou)", "country": "CN"},
    132203: {"name": "Tencent Cloud", "country": "CN"},
    45090: {"name": "Tencent", "country": "CN"},

    # ═══════════════════════════════════════════════════════════════
    # CDN / Edge
    # ═══════════════════════════════════════════════════════════════
    13786: {"name": "Seabone (Sparkle)", "country": "IT"},
    30148: {"name": "Sucuri", "country": "US"},
    209242: {"name": "Cloudflare (WARP)", "country": "US"},
    14789: {"name": "Voxel (Internap)", "country": "US"},
    22822: {"name": "Limelight Networks", "country": "US"},
    35994: {"name": "Akamai", "country": "US"},
    18717: {"name": "Voxility", "country": "RO"},
    46489: {"name": "Twitch", "country": "US"},
    19679: {"name": "Dropbox", "country": "US"},

    # ═══════════════════════════════════════════════════════════════
    # US Tier-1 / Transit
    # ═══════════════════════════════════════════════════════════════
    3356: {"name": "Lumen (CenturyLink/Level 3)", "country": "US"},
    174: {"name": "Cogent Communications", "country": "US"},
    6939: {"name": "Hurricane Electric", "country": "US"},
    2914: {"name": "NTT America", "country": "US"},
    1299: {"name": "Arelion (Telia Carrier)", "country": "SE"},
    3257: {"name": "GTT Communications", "country": "US"},
    6461: {"name": "Zayo", "country": "US"},
    3491: {"name": "PCCW Global", "country": "HK"},
    6762: {"name": "Telecom Italia Sparkle", "country": "IT"},
    1239: {"name": "Sprint", "country": "US"},
    7018: {"name": "AT&T", "country": "US"},
    701: {"name": "Verizon Business", "country": "US"},
    3320: {"name": "Deutsche Telekom (DTAG)", "country": "DE"},
    6830: {"name": "Liberty Global", "country": "NL"},
    5511: {"name": "Orange (OPENTRANSIT)", "country": "FR"},
    6453: {"name": "TATA Communications", "country": "IN"},
    4637: {"name": "Telstra Global", "country": "AU"},

    # ═══════════════════════════════════════════════════════════════
    # US ISPs
    # ═══════════════════════════════════════════════════════════════
    7922: {"name": "Comcast", "country": "US"},
    20115: {"name": "Charter (Spectrum)", "country": "US"},
    22773: {"name": "Cox Communications", "country": "US"},
    11351: {"name": "Charter (Time Warner)", "country": "US"},
    11427: {"name": "Charter (TWC)", "country": "US"},
    7843: {"name": "Charter (Adelphia)", "country": "US"},
    20001: {"name": "Charter (RR)", "country": "US"},
    33588: {"name": "Charter (BHN)", "country": "US"},
    10796: {"name": "Charter (TWC)", "country": "US"},
    209: {"name": "CenturyLink (Qwest)", "country": "US"},
    22394: {"name": "Verizon Wireless", "country": "US"},
    6167: {"name": "Verizon Business (UUNET)", "country": "US"},
    20473: {"name": "Vultr (Choopa)", "country": "US"},
    63949: {"name": "Linode (Akamai)", "country": "US"},
    14061: {"name": "DigitalOcean", "country": "US"},
    3462: {"name": "HiNet (Chunghwa Telecom)", "country": "TW"},

    # ═══════════════════════════════════════════════════════════════
    # European ISPs / Telecoms
    # ═══════════════════════════════════════════════════════════════
    3215: {"name": "Orange (France Telecom)", "country": "FR"},
    12322: {"name": "Free (Proxad)", "country": "FR"},
    15557: {"name": "SFR", "country": "FR"},
    5410: {"name": "Bouygues Telecom", "country": "FR"},
    3303: {"name": "Swisscom", "country": "CH"},
    6805: {"name": "Telefonica Germany", "country": "DE"},
    6830: {"name": "Liberty Global", "country": "NL"},
    8560: {"name": "1&1 IONOS", "country": "DE"},
    31334: {"name": "Vodafone Kabel Deutschland", "country": "DE"},
    6724: {"name": "Strato (1&1)", "country": "DE"},
    680: {"name": "DFN (German Research Network)", "country": "DE"},
    5400: {"name": "BT (British Telecom)", "country": "GB"},
    2856: {"name": "BT (British Telecom)", "country": "GB"},
    5607: {"name": "Sky UK", "country": "GB"},
    6871: {"name": "Plusnet", "country": "GB"},
    13285: {"name": "TalkTalk", "country": "GB"},
    20712: {"name": "Andrews & Arnold", "country": "GB"},
    3209: {"name": "Vodafone Germany", "country": "DE"},
    6805: {"name": "Telefonica Germany", "country": "DE"},
    12389: {"name": "Rostelecom", "country": "RU"},
    31133: {"name": "MegaFon", "country": "RU"},
    8402: {"name": "VEON (Beeline)", "country": "RU"},
    25513: {"name": "PJSC MTS", "country": "RU"},
    12552: {"name": "IPO (Tele2 Sweden)", "country": "SE"},
    2119: {"name": "Telenor", "country": "NO"},
    29518: {"name": "Bredband2", "country": "SE"},
    1257: {"name": "Tele2 (SWIPNET)", "country": "SE"},
    34984: {"name": "Superonline (Turkcell)", "country": "TR"},
    9121: {"name": "Turk Telekom", "country": "TR"},
    15897: {"name": "Vodafone Turkey", "country": "TR"},
    3269: {"name": "Telecom Italia", "country": "IT"},
    12874: {"name": "Fastweb", "country": "IT"},
    30722: {"name": "Vodafone Italia", "country": "IT"},
    3352: {"name": "Telefonica Spain", "country": "ES"},
    12479: {"name": "Orange Spain", "country": "ES"},
    12430: {"name": "Vodafone Spain", "country": "ES"},
    6739: {"name": "ONO (Vodafone Spain Cable)", "country": "ES"},
    5617: {"name": "Polish Telecom (TPSA)", "country": "PL"},
    5588: {"name": "T-Mobile Poland", "country": "PL"},
    12741: {"name": "Netia", "country": "PL"},
    6830: {"name": "UPC (Liberty Global)", "country": "NL"},
    1136: {"name": "KPN", "country": "NL"},
    15542: {"name": "SURFnet", "country": "NL"},
    6848: {"name": "Telenet (Liberty Global)", "country": "BE"},
    5432: {"name": "Proximus (Belgacom)", "country": "BE"},
    47541: {"name": "VK (vk.com)", "country": "RU"},
    2200: {"name": "Renater (French Education)", "country": "FR"},
    47764: {"name": "VK (Mail.ru)", "country": "RU"},

    # ═══════════════════════════════════════════════════════════════
    # Asia-Pacific ISPs
    # ═══════════════════════════════════════════════════════════════
    4134: {"name": "China Telecom", "country": "CN"},
    4837: {"name": "China Unicom", "country": "CN"},
    9808: {"name": "China Mobile", "country": "CN"},
    56040: {"name": "China Mobile", "country": "CN"},
    4766: {"name": "Korea Telecom", "country": "KR"},
    4788: {"name": "TM Net (Telekom Malaysia)", "country": "MY"},
    9299: {"name": "Philippine Long Distance Telephone", "country": "PH"},
    17676: {"name": "SoftBank", "country": "JP"},
    2516: {"name": "KDDI", "country": "JP"},
    2497: {"name": "IIJ (Internet Initiative Japan)", "country": "JP"},
    4713: {"name": "NTT OCN (Japan)", "country": "JP"},
    7527: {"name": "BSNL (India)", "country": "IN"},
    9829: {"name": "BSNL (India)", "country": "IN"},
    55836: {"name": "Reliance Jio", "country": "IN"},
    45609: {"name": "Airtel India", "country": "IN"},
    18209: {"name": "Vodafone Idea (India)", "country": "IN"},
    24560: {"name": "Airtel (Bharti)", "country": "IN"},
    9498: {"name": "BSNL", "country": "IN"},
    4755: {"name": "TATA Communications (VSNL)", "country": "IN"},
    7545: {"name": "TPG Telecom (Australia)", "country": "AU"},
    4764: {"name": "Telstra (REACH)", "country": "AU"},
    1221: {"name": "Telstra", "country": "AU"},
    4826: {"name": "Vocus (Australia)", "country": "AU"},
    9443: {"name": "StarHub (Singapore)", "country": "SG"},
    4657: {"name": "StarHub", "country": "SG"},
    3758: {"name": "SingTel", "country": "SG"},
    9506: {"name": "SingTel (Optus)", "country": "AU"},
    7473: {"name": "SingTel", "country": "SG"},
    24378: {"name": "TrueOnline (Thailand)", "country": "TH"},
    23969: {"name": "TOT (Thailand)", "country": "TH"},
    38001: {"name": "NewMedia Express (SG)", "country": "SG"},
    18106: {"name": "Viewqwest (SG)", "country": "SG"},
    17408: {"name": "NTT (Japan)", "country": "JP"},

    # ═══════════════════════════════════════════════════════════════
    # Latin America
    # ═══════════════════════════════════════════════════════════════
    10318: {"name": "Telefonica (Brazil)", "country": "BR"},
    28573: {"name": "Claro (Brazil)", "country": "BR"},
    7738: {"name": "Telemar (Oi, Brazil)", "country": "BR"},
    22085: {"name": "TIM (Brazil)", "country": "BR"},
    8167: {"name": "Brasil Telecom", "country": "BR"},
    27699: {"name": "Telefonica Argentina", "country": "AR"},
    11664: {"name": "Techtel (Datco)", "country": "AR"},
    7303: {"name": "Telecom Argentina", "country": "AR"},
    8151: {"name": "Telmex (Mexico)", "country": "MX"},
    28548: {"name": "Tigo (Colombia)", "country": "CO"},
    13489: {"name": "EPM Telecomunicaciones", "country": "CO"},
    10299: {"name": "IFX Networks (LatAm)", "country": "CO"},

    # ═══════════════════════════════════════════════════════════════
    # Africa / Middle East
    # ═══════════════════════════════════════════════════════════════
    36943: {"name": "Safaricom (Kenya)", "country": "KE"},
    37100: {"name": "SEACOM", "country": "ZA"},
    36874: {"name": "iWay Africa", "country": "ZA"},
    37271: {"name": "Workonline Communications", "country": "ZA"},
    5713: {"name": "SAIX (South Africa)", "country": "ZA"},
    3741: {"name": "Internet Solutions (ZA)", "country": "ZA"},
    8529: {"name": "Omantel", "country": "OM"},
    5384: {"name": "Emirates Telecom (Etisalat)", "country": "AE"},
    15802: {"name": "du (Emirates)", "country": "AE"},
    8781: {"name": "STC (Saudi Telecom)", "country": "SA"},
    39891: {"name": "Saudi Telecom (STC)", "country": "SA"},
    12880: {"name": "Iran TIC", "country": "IR"},

    # ═══════════════════════════════════════════════════════════════
    # Hosting / Colocation
    # ═══════════════════════════════════════════════════════════════
    24940: {"name": "Hetzner", "country": "DE"},
    16276: {"name": "OVHcloud", "country": "FR"},
    197540: {"name": "Netcup", "country": "DE"},
    51167: {"name": "Contabo", "country": "DE"},
    46606: {"name": "DigitalOcean (NYC)", "country": "US"},
    62567: {"name": "DigitalOcean (SFO)", "country": "US"},
    29802: {"name": "HIVELOCITY", "country": "US"},
    53667: {"name": "FranTech (BuyVM)", "country": "US"},
    25820: {"name": "IT7 Networks", "country": "CA"},
    46844: {"name": "Sharktech", "country": "US"},
    6724: {"name": "Strato (1&1)", "country": "DE"},
    15003: {"name": "Nobis Technology Group", "country": "US"},
    32613: {"name": "iWeb (IWEB)", "country": "CA"},
    19871: {"name": "Network Solutions", "country": "US"},
    30633: {"name": "Leaseweb", "country": "NL"},
    60068: {"name": "Datacamp (CDN77)", "country": "GB"},
    60781: {"name": "LeaseWeb Netherlands", "country": "NL"},
    22612: {"name": "Namecheap", "country": "US"},
    18978: {"name": "Enzu", "country": "US"},
    11878: {"name": "tzulo", "country": "US"},
    23470: {"name": "ReliableSite", "country": "US"},
    198605: {"name": "Avast", "country": "CZ"},
    200019: {"name": "AlexHost", "country": "MD"},

    # ═══════════════════════════════════════════════════════════════
    # DNS / Security / Anti-DDoS
    # ═══════════════════════════════════════════════════════════════
    36692: {"name": "OpenDNS (Cisco Umbrella)", "country": "US"},
    15133: {"name": "Verizon Digital Media (Edgecast)", "country": "US"},
    19551: {"name": "Incapsula (Imperva)", "country": "US"},
    62785: {"name": "NsOne (IBM)", "country": "US"},
    396356: {"name": "Maxcdn (StackPath)", "country": "US"},
    55002: {"name": "Defense.Net", "country": "US"},

    # ═══════════════════════════════════════════════════════════════
    # Education / Research Networks
    # ═══════════════════════════════════════════════════════════════
    11537: {"name": "Internet2", "country": "US"},
    2381: {"name": "ESnet (DOE)", "country": "US"},
    786: {"name": "JANET (UK Research)", "country": "GB"},
    3292: {"name": "TDC (Denmark)", "country": "DK"},
    1930: {"name": "FCCN (Portugal NREN)", "country": "PT"},
    2852: {"name": "CESNET (Czech NREN)", "country": "CZ"},
    2018: {"name": "AFRINIC", "country": "MU"},
    1101: {"name": "SURF (Dutch NREN)", "country": "NL"},

    # ═══════════════════════════════════════════════════════════════
    # IXPs / Route Servers
    # ═══════════════════════════════════════════════════════════════
    6695: {"name": "DE-CIX (Frankfurt)", "country": "DE"},
    1200: {"name": "AMS-IX", "country": "NL"},
    47541: {"name": "VK", "country": "RU"},
    24115: {"name": "Equinix Exchange", "country": "US"},
    8714: {"name": "LINX (London)", "country": "GB"},
    50629: {"name": "LONAP", "country": "GB"},

    # ═══════════════════════════════════════════════════════════════
    # VPN / Privacy
    # ═══════════════════════════════════════════════════════════════
    9009: {"name": "M247 (VPN infrastructure)", "country": "GB"},
    212238: {"name": "Datacamp (Mullvad)", "country": "SE"},
    397423: {"name": "Mullvad VPN", "country": "SE"},

    # ═══════════════════════════════════════════════════════════════
    # Social / SaaS
    # ═══════════════════════════════════════════════════════════════
    14413: {"name": "LinkedIn", "country": "US"},
    62041: {"name": "Telegram", "country": "GB"},
    32590: {"name": "Valve (Steam)", "country": "US"},
    46489: {"name": "Twitch", "country": "US"},
    36040: {"name": "YouTube", "country": "US"},
    19551: {"name": "Incapsula", "country": "US"},
    33070: {"name": "Rackspace", "country": "US"},
    12008: {"name": "Rackspace (UK)", "country": "GB"},
    27357: {"name": "Rackspace", "country": "US"},
    40428: {"name": "Salesforce", "country": "US"},
    8068: {"name": "Microsoft (Azure)", "country": "US"},
    8069: {"name": "Microsoft (Azure)", "country": "US"},
    14576: {"name": "Servicenow", "country": "US"},
    26496: {"name": "GoDaddy", "country": "US"},
    398101: {"name": "GoDaddy (US-West)", "country": "US"},
    27176: {"name": "DataPipe / Rackspace", "country": "US"},
    36408: {"name": "Fastly (Japan)", "country": "JP"},
    54825: {"name": "Packet (Equinix Metal)", "country": "US"},
    11798: {"name": "HostGator", "country": "US"},
    397213: {"name": "Uber", "country": "US"},
    20446: {"name": "Highwinds (StackPath)", "country": "US"},
    30607: {"name": "ProofPoint", "country": "US"},
    16397: {"name": "Latisys (Zayo)", "country": "US"},
    26347: {"name": "New Dream Network (DreamHost)", "country": "US"},
    38283: {"name": "Leaseweb Asia", "country": "SG"},
    14907: {"name": "Wikipedia (Wikimedia)", "country": "US"},
    25459: {"name": "Bytedance (TikTok)", "country": "US"},
    138699: {"name": "Bytedance (TikTok)", "country": "SG"},
    396986: {"name": "Bytedance", "country": "US"},
}


def lookup_asn(asn: int) -> dict | None:
    """Look up a single ASN in the registry.

    Returns the registry entry dict (with 'name' and 'country') or None.
    """
    return ASN_REGISTRY.get(asn)


def batch_lookup_asn(asns: list[int]) -> dict[int, dict]:
    """Look up multiple ASNs and return only those found.

    Returns a dict mapping ASN int -> registry entry for each found ASN.
    """
    results: dict[int, dict] = {}
    for asn in asns:
        entry = ASN_REGISTRY.get(asn)
        if entry is not None:
            results[asn] = entry
    return results
