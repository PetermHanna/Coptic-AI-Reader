"""Turn book text (Coptic, German, Arabic) and recognized audio into one
shared sound alphabet, so they can be compared."""
import re
import subprocess
import unicodedata

# --- Coptic -> IPA (Greco-Bohairic church pronunciation, simplified) ---
DIGRAPHS = {'ⲟⲩ': 'u', 'ⲁⲩ': 'av', 'ⲉⲩ': 'ev', 'ⲏⲩ': 'iv'}
LETTERS = {
    'ⲁ': 'a', 'ⲃ': 'v', 'ⲅ': 'g', 'ⲇ': 'd', 'ⲉ': 'e', 'ⲍ': 'z', 'ⲏ': 'i',
    'ⲑ': 'θ', 'ⲓ': 'i', 'ⲕ': 'k', 'ⲗ': 'l', 'ⲙ': 'm', 'ⲛ': 'n', 'ⲝ': 'ks',
    'ⲟ': 'o', 'ⲡ': 'p', 'ⲣ': 'r', 'ⲥ': 's', 'ⲧ': 't', 'ⲩ': 'i', 'ⲫ': 'f',
    'ⲭ': 'x', 'ⲯ': 'ps', 'ⲱ': 'o', 'ϣ': 'ʃ', 'ϥ': 'f', 'ϧ': 'x', 'ϩ': 'h',
    'ϫ': 'dʒ', 'ϭ': 'tʃ', 'ϯ': 'ti',
}
VOWELS = set('ⲁⲉⲏⲓⲟⲩⲱ')
JINKIM = '̀'


def coptic_to_ipa(text):
    text = unicodedata.normalize('NFD', text.lower())
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        jinkim = i + 1 < len(text) and text[i + 1] == JINKIM
        pair = text[i:i + 2]
        if pair in DIGRAPHS:
            out.append(DIGRAPHS[pair]); i += 2; continue
        if ch in LETTERS:
            if jinkim and ch not in VOWELS:
                out.append('e')  # jinkim: short "e" before the consonant
            if ch == 'ⲅ' and i + 1 < len(text) and text[i + 1] in 'ⲅⲕⲭ':
                out.append('n')
            else:
                out.append(LETTERS[ch])
        elif ch.isspace() or ch in ':.,;':
            out.append(' ')
        i += 1
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def espeak_ipa(text, voice):
    r = subprocess.run(['espeak-ng', '-q', '--ipa', '-v', voice, text],
                       capture_output=True, text=True, check=True)
    return r.stdout.replace('\n', ' ')


def to_ipa(text, lang):
    if lang == 'cop':
        return coptic_to_ipa(text)
    return espeak_ipa(text, {'de': 'de', 'ar': 'ar', 'en': 'en-us'}[lang])


# --- Shared sound classes: similar sounds count as the same letter. ---
# This absorbs most recognizer confusions (b/p, d/t, s/ʃ, e/ɛ/ə ...).
CLASSES = {
    'A': 'aɑæɐʌ', 'E': 'eɛəɘœøɜ', 'I': 'iɪyʏɨj', 'O': 'oɔɒ', 'U': 'uʊɯw',
    'P': 'pb', 'T': 'tdʈɖθð', 'K': 'kgqɡcɟ', 'F': 'fvɸβ', 'S': 'szʃʒɕʂʑç',
    'H': 'xχħhɣʁɦʕ', 'M': 'm', 'N': 'nŋɲɳɴ', 'L': 'lɫɭʎ', 'R': 'rɾɹʀɽ',
}
CHAR2CLASS = {c: k for k, chars in CLASSES.items() for c in chars}
VOWEL_CLASSES = set('AEIOU')


def ipa_to_classes(ipa):
    ipa = unicodedata.normalize('NFD', ipa.replace('ç', 'ʃ'))
    out = []
    for ch in ipa:
        k = CHAR2CLASS.get(ch)
        if k and not (out and out[-1] == k and k in VOWEL_CLASSES):  # merge long vowels
            out.append(k)
    return ''.join(out)
