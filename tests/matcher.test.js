import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Matcher, normalize } from '../src/matcher.js';

const book = JSON.parse(readFileSync(new URL('./fixtures/sample.json', import.meta.url)));
const id = (r) => r?.paragraph.id;

test('normalize strips Arabic diacritics and hamza variants', () => {
  assert.equal(normalize('أبانا الذي في السماوات'), normalize('ابانا الذى فى السماوات'));
  assert.equal(normalize('امحُ معاصيَّ'), 'امح معاصي');
});

test('finds English text with recognition errors', () => {
  const m = new Matcher(book);
  assert.equal(id(m.locate('give us this day our daley bread and for give us')), 'lp-3');
});

test('finds Arabic text without diacritics', () => {
  const m = new Matcher(book);
  assert.equal(id(m.locate('اغسلني كثيرا من اثمي ومن خطيتي', { languages: ['ar', 'cop_ar'] })), 'ps50-2');
});

test('finds Coptic via Arabic-letter transliteration', () => {
  const m = new Matcher(book);
  assert.equal(id(m.locate('بينيوت ات خين ني فيوي ماريف', { languages: ['ar', 'cop_ar'] })), 'lp-1');
});

test('repeated text prefers the paragraph right after the current one', () => {
  const m = new Matcher(book);
  const phrase = 'holy god holy mighty holy immortal';
  m.jumpTo(book.paragraphs.findIndex((p) => p.id === 'tri-1'));
  assert.equal(id(m.locate(phrase + ' who was crucified')), 'tri-2');
  assert.equal(id(m.locate(phrase + ' who rose from')), 'tri-3');
});

test('a similar verse nearby does not hide the right one further on', () => {
  const m = new Matcher(book);
  assert.equal(id(m.locate('قدوس الله قدوس القوي قدوس الحي الذي لا يموت الذي صلب عنا', { languages: ['ar'] })), 'tri-2');
});

test('follows German speech', () => {
  const m = new Matcher(book);
  assert.equal(id(m.locate('unser tägliches brot gib uns heute und vergib uns', { languages: ['de'] })), 'lp-3');
});

test('unrelated speech does not move the position', () => {
  const m = new Matcher(book);
  assert.equal(m.locate('please turn off your mobile phones before we start'), null);
});
