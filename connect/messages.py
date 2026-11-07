"""Step 3: every word the owner reads, in Finnish, Swedish, Norwegian and English.

Dates, hours and names are filled in by code, so no text can change them.
"""
from __future__ import annotations

from datetime import date

LANGUAGES = ("fi", "sv", "nb", "en")
MIN_VIEWS_TO_MENTION = 20  # A smaller number is no reason to act, so the message doesn't quote it.

DAY_NAMES = {
    "XMAS_EVE": ("Jouluaatto", "Julafton", "Julaften", "Christmas Eve"),
    "XMAS_DAY": ("Joulupäivä", "Juldagen", "1. juledag", "Christmas Day"),
    "BOXING_DAY": ("Tapaninpäivä", "Annandag jul", "2. juledag", "Boxing Day"),
    "DEC23": ("Aatonaatto", "Lillejulafton", "Lille julaften", "23 December"),
    "INTERDAY": ("Välipäivä", "Mellandag", "Romjul", "Between the holidays"),
    "NYE": ("Uudenvuodenaatto", "Nyårsafton", "Nyttårsaften", "New Year's Eve"),
    "NEW_YEARS_DAY": ("Uudenvuodenpäivä", "Nyårsdagen", "1. nyttårsdag", "New Year's Day"),
    "EPIPHANY_EVE": ("Loppiaisaatto", "Trettondagsafton", "Helligtrekongersaften", "Epiphany Eve"),
    "EPIPHANY": ("Loppiainen", "Trettondedag jul", "Helligtrekongersdag", "Epiphany"),
    "INDEPENDENCE_DAY": ("Itsenäisyyspäivä", "Finlands självständighetsdag", "Finlands uavhengighetsdag",
                         "Finnish Independence Day"),
    "FATHERS_DAY": ("Isänpäivä", "Fars dag", "Farsdag", "Father's Day"),
    "LUCIA": ("Lucianpäivä", "Lucia", "Luciadagen", "St Lucia's Day"),
    "BLACK_FRIDAY": ("Black Friday", "Black Friday", "Black Friday", "Black Friday"),
    "ALL_SAINTS": ("Pyhäinpäivä", "Alla helgons dag", "Allehelgensdag", "All Saints' Day"),
    "EVENT": ("Tapahtumailta", "Evenemangskväll", "Arrangementskveld", "Event night"),
    "SCHOOL_BREAK": ("Koulujen loma", "Skollov", "Skoleferie", "School holiday"),
}
WEEKDAYS = {
    "fi": ("ma", "ti", "ke", "to", "pe", "la", "su"),
    "sv": ("mån", "tis", "ons", "tors", "fre", "lör", "sön"),
    "nb": ("man", "tir", "ons", "tor", "fre", "lør", "søn"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

TEXT = {
    "fi": {
        "closed": "kiinni", "normal": "normaalit aukioloajat",
        "intro": "Hei {first}! {business} näkyy Googlessa näinä päivinä todennäköisesti väärin:",
        "line": "• {day} {date}: Google näyttää {shown}. Ehdotamme: {proposed}. {reason}.",
        "ask": "Emme ole tästä täysin varmoja, joten kerrothan, pitääkö ehdotus paikkansa.",
        "new_customer": "Teiltä ei ole vielä aiempia poikkeusaikoja, joten vertasimme vastaaviin yrityksiin.",
        "value": "Samoina päivinä viime vuonna yrityksellänne oli noin {n} hakunäyttöä Googlessa.",
        "cta": "Hyväksy, muokkaa tai kieltäydy ilman kirjautumista: {link}",
        "subject": "{business}: tarkistathan poikkeusaukiolot",
        "LAST_YEAR": "Viime vuonna: {last}", "SHOPPING_CENTRE": "{mall}: {mall_hours}",
        "PEERS": "{share} % vastaavista yrityksistä, jotka merkitsivät aikansa, oli kiinni",
        "OLDER_YEAR": "Kaksi vuotta sitten: {older}", "REVIEW_TIME": "Asiakkaan mukaan suljitte viime vuonna klo {close}", "REVIEW_CLOSED": "Asiakkaat löysivät ovet kiinni viime vuonna", "REVIEW_WEEK": "Asiakkaan mukaan aukiolonne ovat nyt {week}", "PATTERN": "Perustuu tietoihimme yrityksestänne ja vastaavista yrityksistä",
        "YOUR_CHOICE": "Aiempi valintanne: {your}",
        "confirm": "Kiitos {first}! Päivitimme yrityksen {business} tiedot:",
        "confirm_line": "• {day} {date}: {final}",
        "where": "Uudet ajat näkyvät: {places}.",
        "more_places": "ja {n} muuta",
        "failed": "Tallennus ei vielä onnistunut, joten mitään ei muutettu. Yritämme uudelleen ja kerromme, kun se on tehty.",
        "standing_offer": "Hoidetaanko jatkossa juhlapyhät puolestasi? Kerromme aina muutoksesta, ja voit perua sen yhdellä napautuksella: {link}",
        "declined": "Selvä {first}, emme muuttaneet mitään. Muistamme tämän seuraavalla kerralla.",
        "auto": "Hei {first}! Päivitimme luvallasi yrityksen {business} juhlapyhien ajat:",
        "undo_link": "Väärin? Peru yhdellä napautuksella: {link}",
        "undone": "Selvä {first}, peruimme muutoksen. {day} {date} näkyy taas kuten ennen.",
        "reminder": "Hei {first}! {business} näkyy yhä väärin {date}. Yksi napautus riittää, ilman kirjautumista: {link}",
        "eta": ("noin {n} min", "noin {n} t", "noin {n} pv"),
    },
    "sv": {
        "closed": "stängt", "normal": "vanliga öppettider",
        "intro": "Hej {first}! {business} visas troligen fel på Google de här dagarna:",
        "line": "• {day} {date}: Google visar {shown}. Vi föreslår: {proposed}. {reason}.",
        "ask": "Vi är inte helt säkra, så berätta gärna om förslaget stämmer.",
        "new_customer": "Vi har inga tidigare avvikande tider för er än, så vi jämförde med liknande företag.",
        "value": "Samma dagar förra året hade ert företag cirka {n} sökvisningar på Google.",
        "cta": "Godkänn, ändra eller tacka nej utan inloggning: {link}",
        "subject": "{business}: kontrollera era avvikande öppettider",
        "LAST_YEAR": "Förra året: {last}", "SHOPPING_CENTRE": "{mall}: {mall_hours}",
        "PEERS": "{share} % av liknande företag som angav sina tider hade stängt",
        "OLDER_YEAR": "För två år sedan: {older}", "REVIEW_TIME": "Enligt en kund stängde ni {close} förra året", "REVIEW_CLOSED": "Kunder stod framför stängd dörr förra året", "REVIEW_WEEK": "Enligt en kund har ni nu öppet {week}", "PATTERN": "Bygger på vad vi vet om ert företag och liknande företag",
        "YOUR_CHOICE": "Ert tidigare val: {your}",
        "confirm": "Tack {first}! Vi har uppdaterat {business}:",
        "confirm_line": "• {day} {date}: {final}",
        "where": "De nya tiderna syns: {places}.",
        "more_places": "och {n} till",
        "failed": "Det gick inte att spara ännu, så inget har ändrats. Vi försöker igen och hör av oss när det är klart.",
        "standing_offer": "Ska vi sköta helgdagarna åt dig i fortsättningen? Vi berättar alltid om ändringen, och du kan ångra den med ett tryck: {link}",
        "declined": "Okej {first}, vi ändrade ingenting. Vi kommer ihåg det till nästa gång.",
        "auto": "Hej {first}! Med ditt tillstånd har vi uppdaterat helgtiderna för {business}:",
        "undo_link": "Fel? Ångra med ett tryck: {link}",
        "undone": "Okej {first}, vi har ångrat ändringen. {day} {date} visas som tidigare igen.",
        "reminder": "Hej {first}! {business} visas fortfarande fel {date}. Ett tryck räcker, ingen inloggning: {link}",
        "eta": ("cirka {n} min", "cirka {n} tim", "cirka {n} dygn"),
    },
    "nb": {
        "closed": "stengt", "normal": "vanlige åpningstider",
        "intro": "Hei {first}! {business} vises trolig feil på Google disse dagene:",
        "line": "• {day} {date}: Google viser {shown}. Vi foreslår: {proposed}. {reason}.",
        "ask": "Vi er ikke helt sikre, så si gjerne fra om forslaget stemmer.",
        "new_customer": "Vi har ingen tidligere avvikende tider for dere ennå, så vi sammenlignet med lignende bedrifter.",
        "value": "De samme dagene i fjor hadde bedriften deres omtrent {n} søkevisninger på Google.",
        "cta": "Godkjenn, endre eller takk nei uten innlogging: {link}",
        "subject": "{business}: sjekk de avvikende åpningstidene",
        "LAST_YEAR": "I fjor: {last}", "SHOPPING_CENTRE": "{mall}: {mall_hours}",
        "PEERS": "{share} % av lignende bedrifter som oppga tidene sine, holdt stengt",
        "OLDER_YEAR": "For to år siden: {older}", "REVIEW_TIME": "Ifølge en kunde stengte dere {close} i fjor", "REVIEW_CLOSED": "Kunder sto foran stengt dør i fjor", "REVIEW_WEEK": "Ifølge en kunde har dere nå åpent {week}", "PATTERN": "Basert på det vi vet om bedriften deres og lignende bedrifter",
        "YOUR_CHOICE": "Deres tidligere valg: {your}",
        "confirm": "Takk {first}! Vi har oppdatert {business}:",
        "confirm_line": "• {day} {date}: {final}",
        "where": "De nye tidene vises: {places}.",
        "more_places": "og {n} til",
        "failed": "Vi fikk ikke lagret ennå, så ingenting er endret. Vi prøver igjen og sier fra når det er gjort.",
        "standing_offer": "Skal vi ta oss av helligdagene for deg fra nå av? Vi sier alltid fra om endringen, og du kan angre med ett trykk: {link}",
        "declined": "Greit {first}, vi endret ingenting. Vi husker det til neste gang.",
        "auto": "Hei {first}! Med din tillatelse har vi oppdatert helligdagstidene for {business}:",
        "undo_link": "Feil? Angre med ett trykk: {link}",
        "undone": "Greit {first}, vi har angret endringen. {day} {date} vises som før igjen.",
        "reminder": "Hei {first}! {business} vises fortsatt feil {date}. Ett trykk holder, uten innlogging: {link}",
        "eta": ("omtrent {n} min", "omtrent {n} t", "omtrent {n} døgn"),
    },
    "en": {
        "closed": "closed", "normal": "regular hours",
        "intro": "Hi {first}! {business} probably shows the wrong hours on Google on these days:",
        "line": "• {day} {date}: Google shows {shown}. We suggest: {proposed}. {reason}.",
        "ask": "We're not fully sure, so please tell us if this is right.",
        "new_customer": "We don't have any earlier special hours for you yet, so we compared similar businesses.",
        "value": "On the same days last year, your business had about {n} search views on Google.",
        "cta": "Approve, edit or decline with no login: {link}",
        "subject": "{business}: please check your special opening hours",
        "LAST_YEAR": "Last year: {last}", "SHOPPING_CENTRE": "{mall}: {mall_hours}",
        "PEERS": "{share}% of similar businesses that entered their hours were closed",
        "OLDER_YEAR": "Two years ago: {older}", "REVIEW_TIME": "A customer says you closed at {close} last year", "REVIEW_CLOSED": "Customers found you closed last year", "REVIEW_WEEK": "A customer says you're now open {week}", "PATTERN": "Based on what we know about your business and similar ones",
        "YOUR_CHOICE": "Your earlier choice: {your}",
        "confirm": "Thanks {first}! We've updated {business}:",
        "confirm_line": "• {day} {date}: {final}",
        "where": "The new hours will show: {places}.",
        "more_places": "and {n} more",
        "failed": "We couldn't save this yet, so nothing has changed. We'll try again and tell you when it's done.",
        "standing_offer": "Want us to handle public holidays for you from now on? We always tell you about a change, and you can undo it in one tap: {link}",
        "declined": "OK {first}, we didn't change anything. We'll remember this next time.",
        "auto": "Hi {first}! With your permission, we've updated the holiday hours for {business}:",
        "undo_link": "Wrong? Undo in one tap: {link}",
        "undone": "OK {first}, we've undone the change. {day} {date} shows as it did before.",
        "reminder": "Hi {first}! {business} still shows the wrong hours on {date}. One tap is enough, with no login: {link}",
        "eta": ("about {n} min", "about {n} h", "about {n} days"),
    },
}

# The words on the owner's approval page.
UI = {
    "fi": {"tell_title": "Tai kerro omin sanoin", "tell_ph": "Esim. jouluaattona suljetaan kahdelta, muuten ok", "tell_send": "Lähetä", "tell_busy": "Luetaan viestiäsi…", "tell_check": "Ymmärsinkö oikein?", "tell_yes": "Kyllä, tallenna", "tell_wrong": "Ei, korjaan", "tell_unavailable": "Emme saaneet tästä selvää juuri nyt. Voit käyttää painikkeita.", "tell_regular": "Normaalit aukioloajat päivitetty", "tell_you": "Kirjoitit", "tell_again": "Kerrothan vielä päivän ja kellonajan.", "tell_no_change": "Ei muutosta", "tell_holidays": "Juhlapyhät", "tell_ask_first": "Kysytään ensin", "tell_automatic": "Hoidetaan puolestasi", "tell_before": "Ennen", "tell_after": "Jälkeen", "alternative": "Siirrä kuten viimeksi: {hours}", "title": "Tarkista aukioloajat", "shown": "Google näyttää nyt", "suggest": "Ehdotus", "why": "Miksi",
           "approve_all": "Hyväksy", "approve_all_n": "Hyväksy kaikki ({n})", "approve": "Hyväksy", "edit": "Muokkaa",
           "decline": "Ei kiitos", "closed_toggle": "Kiinni koko päivän", "from": "Avataan", "to": "Suljetaan",
           "add_period": "Lisää toinen aukiolojakso", "remove_period": "Poista toinen jakso", "save": "Tallenna",
           "cancel": "Peruuta", "why_decline": "Miksi ei? Vastaus on vapaaehtoinen.",
           "r_open_as_usual": "Olemme auki normaalisti", "r_dont_ask": "Älä kysy tästä päivästä enää",
           "r_wrong": "Ehdotus on muuten väärin", "r_stop": "Älä lähetä näitä viestejä", "skip": "Ohita",
           "done_title": "Valmis!", "declined_title": "Selvä, emme muuttaneet mitään.",
           "where": "Missä uudet ajat näkyvät", "undo": "Peru muutos", "undone": "Peruttu",
           "standing_q": "Hoidetaanko jatkossa juhlapyhät puolestasi?",
           "standing_d": "Kerromme aina muutoksesta, ja voit perua sen yhdellä napautuksella.",
           "standing_yes": "Kyllä, hoitakaa", "standing_no": "Ei nyt", "standing_on": "Selvä, hoidamme juhlapyhät jatkossa.",
           "standing_off": "Lopeta automaattiset päivitykset", "no_login": "Ei kirjautumista. Sinä päätät aina.",
           "ask": "Emme ole varmoja. Pitääkö tämä paikkansa?", "views": "{n} hakunäyttöä viime vuonna",
           "saving": "Tallennetaan…", "failed": "Tallennus ei onnistunut, joten mitään ei muutettu. Yritämme uudelleen.",
           "invalid": "Tarkista ajat.", "expired": "Tämä linkki ei ole enää voimassa.",
           "stopped": "Selvä, emme lähetä näitä viestejä enää.", "pending_write": "Odottaa tallennusta"},
    "sv": {"tell_title": "Eller säg det med egna ord", "tell_ph": "T.ex. på julafton stänger vi klockan två, annars ok", "tell_send": "Skicka", "tell_busy": "Läser ditt meddelande…", "tell_check": "Förstod jag rätt?", "tell_yes": "Ja, spara", "tell_wrong": "Nej, jag ändrar", "tell_unavailable": "Vi kunde inte tolka det just nu. Du kan använda knapparna.", "tell_regular": "De vanliga öppettiderna är uppdaterade", "tell_you": "Du skrev", "tell_again": "Berätta gärna vilken dag och vilken tid du menar.", "tell_no_change": "Ingen ändring", "tell_holidays": "Helgdagar", "tell_ask_first": "Vi frågar först", "tell_automatic": "Vi sköter det åt dig", "tell_before": "Före", "tell_after": "Efter", "alternative": "Flytta som förra gången: {hours}", "title": "Kontrollera öppettiderna", "shown": "Google visar nu", "suggest": "Förslag", "why": "Varför",
           "approve_all": "Godkänn", "approve_all_n": "Godkänn alla ({n})", "approve": "Godkänn", "edit": "Ändra",
           "decline": "Nej tack", "closed_toggle": "Stängt hela dagen", "from": "Öppnar", "to": "Stänger",
           "add_period": "Lägg till en andra öppettid", "remove_period": "Ta bort den andra öppettiden", "save": "Spara",
           "cancel": "Avbryt", "why_decline": "Varför inte? Svaret är frivilligt.",
           "r_open_as_usual": "Vi har öppet som vanligt", "r_dont_ask": "Fråga inte om den här dagen igen",
           "r_wrong": "Förslaget är fel på annat sätt", "r_stop": "Skicka inte fler sådana meddelanden", "skip": "Hoppa över",
           "done_title": "Klart!", "declined_title": "Okej, vi ändrade ingenting.",
           "where": "Här syns de nya tiderna", "undo": "Ångra ändringen", "undone": "Ångrad",
           "standing_q": "Ska vi sköta helgdagarna åt dig i fortsättningen?",
           "standing_d": "Vi berättar alltid om ändringen, och du kan ångra den med ett tryck.",
           "standing_yes": "Ja, gör det", "standing_no": "Inte nu", "standing_on": "Okej, vi sköter helgdagarna från och med nu.",
           "standing_off": "Stäng av automatiska uppdateringar", "no_login": "Ingen inloggning. Du bestämmer alltid.",
           "ask": "Vi är inte säkra. Stämmer det här?", "views": "{n} sökvisningar förra året",
           "saving": "Sparar…", "failed": "Det gick inte att spara, så inget har ändrats. Vi försöker igen.",
           "invalid": "Kontrollera tiderna.", "expired": "Den här länken gäller inte längre.",
           "stopped": "Okej, vi skickar inga fler sådana meddelanden.", "pending_write": "Väntar på att sparas"},
    "nb": {"tell_title": "Eller si det med egne ord", "tell_ph": "F.eks. på julaften stenger vi klokka to, ellers ok", "tell_send": "Send", "tell_busy": "Leser meldingen din…", "tell_check": "Forsto jeg riktig?", "tell_yes": "Ja, lagre", "tell_wrong": "Nei, jeg endrer", "tell_unavailable": "Vi fikk ikke tak i det akkurat nå. Du kan bruke knappene.", "tell_regular": "De vanlige åpningstidene er oppdatert", "tell_you": "Du skrev", "tell_again": "Si gjerne hvilken dag og hvilket klokkeslett du mener.", "tell_no_change": "Ingen endring", "tell_holidays": "Helligdager", "tell_ask_first": "Vi spør først", "tell_automatic": "Vi ordner det for deg", "tell_before": "Før", "tell_after": "Etter", "alternative": "Flytt som sist: {hours}", "title": "Sjekk åpningstidene", "shown": "Google viser nå", "suggest": "Forslag", "why": "Hvorfor",
           "approve_all": "Godkjenn", "approve_all_n": "Godkjenn alle ({n})", "approve": "Godkjenn", "edit": "Endre",
           "decline": "Nei takk", "closed_toggle": "Stengt hele dagen", "from": "Åpner", "to": "Stenger",
           "add_period": "Legg til en åpningsperiode til", "remove_period": "Fjern den andre perioden", "save": "Lagre",
           "cancel": "Avbryt", "why_decline": "Hvorfor ikke? Svaret er frivillig.",
           "r_open_as_usual": "Vi har åpent som vanlig", "r_dont_ask": "Ikke spør om denne dagen igjen",
           "r_wrong": "Forslaget er feil på en annen måte", "r_stop": "Ikke send flere slike meldinger", "skip": "Hopp over",
           "done_title": "Ferdig!", "declined_title": "Greit, vi endret ingenting.",
           "where": "Her vises de nye tidene", "undo": "Angre endringen", "undone": "Angret",
           "standing_q": "Skal vi ta oss av helligdagene for deg fra nå av?",
           "standing_d": "Vi sier alltid fra om endringen, og du kan angre med ett trykk.",
           "standing_yes": "Ja, gjør det", "standing_no": "Ikke nå", "standing_on": "Greit, vi tar oss av helligdagene fra nå av.",
           "standing_off": "Slå av automatiske oppdateringer", "no_login": "Ingen innlogging. Du bestemmer alltid.",
           "ask": "Vi er ikke sikre. Stemmer dette?", "views": "{n} søkevisninger i fjor",
           "saving": "Lagrer…", "failed": "Vi fikk ikke lagret, så ingenting er endret. Vi prøver igjen.",
           "invalid": "Sjekk tidene.", "expired": "Denne lenken gjelder ikke lenger.",
           "stopped": "Greit, vi sender ikke flere slike meldinger.", "pending_write": "Venter på lagring"},
    "en": {"tell_title": "Or say it in your own words", "tell_ph": "E.g. we close at two on Christmas Eve, otherwise fine", "tell_send": "Send", "tell_busy": "Reading your message…", "tell_check": "Did I get that right?", "tell_yes": "Yes, save it", "tell_wrong": "No, let me change it", "tell_unavailable": "We couldn't work that out just now. You can use the buttons.", "tell_regular": "Regular hours updated", "tell_you": "You wrote", "tell_again": "Please tell us which day and what time you mean.", "tell_no_change": "No change", "tell_holidays": "Public holidays", "tell_ask_first": "We ask first", "tell_automatic": "We handle them for you", "tell_before": "Before", "tell_after": "After", "alternative": "Move like last time: {hours}", "title": "Check your opening hours", "shown": "Google shows now", "suggest": "Suggestion", "why": "Why",
           "approve_all": "Approve", "approve_all_n": "Approve all ({n})", "approve": "Approve", "edit": "Edit",
           "decline": "No thanks", "closed_toggle": "Closed all day", "from": "Opens", "to": "Closes",
           "add_period": "Add a second opening period", "remove_period": "Remove the second period", "save": "Save",
           "cancel": "Cancel", "why_decline": "Why not? Answering is optional.",
           "r_open_as_usual": "We're open as usual", "r_dont_ask": "Don't ask about this day again",
           "r_wrong": "The suggestion is wrong in another way", "r_stop": "Don't send me these messages", "skip": "Skip",
           "done_title": "Done!", "declined_title": "OK, we didn't change anything.",
           "where": "Where the new hours show", "undo": "Undo this change", "undone": "Undone",
           "standing_q": "Want us to handle public holidays for you from now on?",
           "standing_d": "We always tell you about a change, and you can undo it in one tap.",
           "standing_yes": "Yes, handle them", "standing_no": "Not now", "standing_on": "OK, we'll handle public holidays from now on.",
           "standing_off": "Turn off automatic updates", "no_login": "No login. You always decide.",
           "ask": "We're not sure. Is this right?", "views": "{n} search views last year",
           "saving": "Saving…", "failed": "We couldn't save this, so nothing has changed. We'll try again.",
           "invalid": "Please check the times.", "expired": "This link is no longer valid.",
           "stopped": "OK, we won't send these messages any more.", "pending_write": "Waiting to be saved"},
}


def language_for(preferred: str | None) -> str:
    return preferred if preferred in LANGUAGES else "en"


def day_name(day_key: str, lang: str, fallback: str = "") -> str:
    names = DAY_NAMES.get(day_key)
    return names[LANGUAGES.index(lang)] if names else (fallback or day_key)


def date_label(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    weekday = WEEKDAYS[lang][d.weekday()]
    if lang == "en":
        return f"{weekday} {d.day} {MONTHS_EN[d.month - 1]}"
    if lang == "sv":
        return f"{weekday} {d.day}/{d.month}"
    return f"{weekday} {d.day}.{d.month}."


def _time(value: str, lang: str) -> str:
    hour, minute = value.split(":")
    separator = ":" if lang == "en" else "."
    return str(int(hour)) + ("" if minute == "00" else separator + minute)


def hours_label(hours: str | None, lang: str) -> str:
    """'07:30-13:00' becomes '7.30–13'. 'REGULAR' and 'closed' become words."""
    if hours == "REGULAR":
        return TEXT[lang]["normal"]
    if not hours or hours == "closed":
        return TEXT[lang]["closed"]
    if hours == "00:00-23:59":
        return "24 h"
    return ", ".join("–".join(_time(x, lang) for x in part.split("-")) for part in hours.split(","))


def reason(item: dict, lang: str) -> str:
    """One short reason, with the numbers behind it. Empty if there is no stored evidence."""
    t = TEXT[lang]
    basis, evidence = item.get("basis"), item.get("evidence") or {}
    if basis == "LAST_YEAR":
        text = t["LAST_YEAR"].format(last=hours_label(evidence.get("last_hours"), lang))
    elif basis == "SHOPPING_CENTRE":
        text = t["SHOPPING_CENTRE"].format(mall=evidence.get("mall", ""),
                                           mall_hours=hours_label(evidence.get("mall_hours"), lang))
    elif basis == "PEERS":
        text = t["PEERS"].format(share=round(evidence.get("peer_share", 0) * 100))
    elif basis == "YOUR_CHOICE":
        text = t["YOUR_CHOICE"].format(your=hours_label(evidence.get("your_hours"), lang))
    elif basis == "OLDER_YEAR":
        text = t["OLDER_YEAR"].format(older=hours_label(evidence.get("older_hours"), lang))
    elif basis == "REVIEW_TIME":
        text = t["REVIEW_TIME"].format(close=_time(evidence.get("close_time", "00:00"), lang))
    elif basis == "REVIEW_WEEK":
        text = t["REVIEW_WEEK"].format(week=hours_label(evidence.get("week_hours"), lang))
    elif basis in ("REVIEW_CLOSED", "PATTERN"):
        text = t[basis]
    else:
        return ""
    return text


def eta_label(seconds: int, lang: str) -> str:
    minute, hour, day = TEXT[lang]["eta"]
    if seconds < 3600:
        return minute.format(n=max(1, round(seconds / 60)))
    if seconds < 86400:
        return hour.format(n=round(seconds / 3600))
    text = day.format(n=round(seconds / 86400))
    return text.replace("1 days", "1 day") if lang == "en" else text


def round_views(n: int) -> int:
    return int(round(n, -1)) if n >= 100 else int(n)


def _line(item: dict, lang: str) -> str:
    return TEXT[lang]["line"].format(
        day=day_name(item["day_key"], lang, item.get("day_name_local", "")), date=date_label(item["date"], lang),
        shown=hours_label(item["shown"], lang), proposed=hours_label(item["proposed"], lang), reason=reason(item, lang))


def offer(first: str, business: str, items: list, link: str, lang: str, channel: str = "SMS",
          no_history: bool = False) -> str:
    """The first message. An email adds a subject line. Every channel carries the suggestion and the reason."""
    t = TEXT[lang]
    parts = [t["intro"].format(first=first, business=business), *[_line(i, lang) for i in items]]
    if no_history:
        parts.append(t["new_customer"])
    if any(i.get("mode") == "ASK" for i in items):
        parts.append(t["ask"])
    total_views = sum(i.get("expected_views") or 0 for i in items)
    if items and all(i.get("views_from_last_year") for i in items) and total_views >= MIN_VIEWS_TO_MENTION:
        parts.append(t["value"].format(n=round_views(total_views)))
    parts.append(t["cta"].format(link=link))
    body = "\n".join(parts)
    if channel == "EMAIL":
        return t["subject"].format(business=business) + "\n\n" + body
    return body


def _final_lines(items: list, lang: str) -> list:
    return [TEXT[lang]["confirm_line"].format(day=day_name(i["day_key"], lang, i.get("day_name_local", "")),
                                              date=date_label(i["date"], lang),
                                              final=hours_label(i["final_hours"], lang)) for i in items]


def places_label(listings: list, lang: str) -> str:
    label = ", ".join(f"{x['name']} {eta_label(x['seconds'], lang)}" for x in listings[:4])
    extra = len(listings) - 4
    return f"{label} {TEXT[lang]['more_places'].format(n=extra)}" if extra > 0 else label


def confirmation(first: str, business: str, items: list, listings: list, lang: str, standing_link: str | None = None) -> str:
    t = TEXT[lang]
    parts = [t["confirm"].format(first=first, business=business), *_final_lines(items, lang)]
    if listings:
        parts.append(t["where"].format(places=places_label(listings, lang)))
    if standing_link:
        parts.append(t["standing_offer"].format(link=standing_link))
    return "\n".join(parts)


def group_weekdays(after: dict, before: dict) -> list:
    """Neighbouring weekdays with the same change become one line: Mon-Fri."""
    order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    groups = []
    for day in order:
        if day not in after:
            continue
        last = groups[-1] if groups else None
        if last and last["after"] == after[day] and last["before"] == before.get(day) and order.index(last["days"][-1]) == order.index(day) - 1:
            last["days"].append(day)
        else:
            groups.append({"days": [day], "after": after[day], "before": before.get(day)})
    return groups


def weekday_span(days: list, lang: str) -> str:
    order = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    names = [WEEKDAYS[lang][order.index(day)] for day in days]
    return names[0] if len(names) == 1 else f"{names[0]}–{names[-1]}"


def regular_confirmation(first: str, business: str, groups: list, listings: list, lang: str) -> str:
    t = TEXT[lang]
    parts = [t["confirm"].format(first=first, business=business)]
    parts += [f"• {weekday_span(g['days'], lang)}: {hours_label(g['after'], lang)}" for g in groups]
    if listings:
        parts.append(t["where"].format(places=places_label(listings, lang)))
    return "\n".join(parts)


def auto_applied(first: str, business: str, items: list, listings: list, link: str, lang: str) -> str:
    t = TEXT[lang]
    parts = [t["auto"].format(first=first, business=business), *_final_lines(items, lang)]
    if listings:
        parts.append(t["where"].format(places=places_label(listings, lang)))
    parts.append(t["undo_link"].format(link=link))
    return "\n".join(parts)


def declined(first: str, lang: str) -> str:
    return TEXT[lang]["declined"].format(first=first)


def write_failed(lang: str) -> str:
    return TEXT[lang]["failed"]


def undone(first: str, item: dict, lang: str) -> str:
    return TEXT[lang]["undone"].format(first=first, day=day_name(item["day_key"], lang, item.get("day_name_local", "")),
                                       date=date_label(item["date"], lang))


def reminder(first: str, business: str, items: list, link: str, lang: str) -> str:
    dates = ", ".join(date_label(i["date"], lang) for i in items)
    return TEXT[lang]["reminder"].format(first=first, business=business, date=dates, link=link)
