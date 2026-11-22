# Coptic AI Reader

An app for church: it **listens to the service and shows you where you are in the prayer book**. It highlights the paragraph and the word being read right now, and keeps scrolling as the service goes on.

![screenshot](docs/screenshot.png)

## Cost: free

- **Speech recognition**: the browser's built-in Web Speech API (Chrome, Edge, Safari, Android, iPhone). No API key, no server, no fees.
- **Matching**: a small JavaScript file (`src/matcher.js`) that runs on the phone itself. No AI service is called.
- **Hosting**: plain static files. Free on GitHub Pages, Netlify or Cloudflare Pages.

## How it works

1. The phone's speech recognizer turns what the priest or deacon says into text.
2. The matcher compares the last ~8 words against every column of the book, using fuzzy letter-trigram matching. This tolerates misheard words, missing Arabic diacritics and spelling differences.
3. Text just ahead of the current position gets a bonus, so repeated prayers (e.g. the Trisagion's "Holy God, Holy Mighty…") move forward instead of jumping back.
4. **Coptic trick**: no speech recognizer understands Coptic. But if the service language is set to *Arabic / Coptic*, the Arabic recognizer writes Coptic *sounds* in Arabic letters. Those get matched against the book's "قبطي معرب" (Coptic in Arabic letters) column. The English recognizer does the same with the "Coptic in English letters" column.

## Run it

```bash
npm start        # serves on http://localhost:8080
npm test         # matcher tests
```

The microphone only works on `https://` or `localhost`. To test without speaking, open **"Test without a microphone"** and type a few words.

## Adding prayer books

A book is one JSON file (see `books/sample.json`):

```json
{
  "title": "...",
  "languages": { "en": "English", "cop": "Coptic", "cop_ar": "قبطي معرب", "ar": "عربي" },
  "paragraphs": [
    { "id": "lp-1", "section": "optional heading",
      "text": { "en": "...", "cop": "...", "cop_ar": "...", "ar": "..." } }
  ]
}
```

Load your own book with **"Open book…"**. Including the `cop_ar` / `cop_lat` transliteration columns is what makes Coptic parts trackable.

## Known limits and next steps

- Firefox has no built-in speech recognition.
- Chrome's free recognizer sends audio to Google's servers. Safari on iOS can recognize speech on the device.
- Fully offline option for later: run the open-source Whisper model inside the browser with `transformers.js` (still free, but a ~40–150 MB download and slower on old phones).
- Content: full liturgies (St. Basil, Agpeya, Psalmody…) need to be converted to the JSON format. Check that you have permission to use each translation.
