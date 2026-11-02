// Run with: node test_web_metadata.js
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.env.METADATA_TEST_SOURCE || 'web/app.js', 'utf8');
const start = source.indexOf("    const bookMetadataStatus = $('book-metadata-status');");
const end = source.indexOf("    ['title', 'output_dir', 'model'", start);
assert.ok(start >= 0 && end > start);
const field = () => ({ value: '', listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; } });
const form = { elements: { title: field(), author: field(), output_dir: field() } };
const inputSource = field();
const status = { textContent: '' };
const profile = { hidden: true };
const nodes = { 'book-metadata-status': status, 'book-profile': profile };
['book-original-title', 'book-original-author', 'book-source', 'book-publication-date',
    'book-export-created', 'book-export-updated', 'book-exported-chapters', 'book-identifier', 'book-model']
    .forEach(id => { nodes[id] = { textContent: '' }; });
const requests = [];
const context = {
    form, inputSource, AbortController, URLSearchParams, $: id => nodes[id] || null,
    saveForm() {}, scheduleEstimate() {}, setTimeout() {}, clearTimeout() {},
    fetch: (url, options) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject })),
};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const api = vm.runInContext('({ refreshBookMetadata })', context);
const info = (title, author) => ({ available: true, title, author, original_title: title, original_author: author,
    book_id: 'urn:uuid:fixture', exported_chapters: 7, export_created_at: '2026-11-01T01:00:00Z', translation_model: 'deepseek-flash' });
function reply(index, data) { requests[index].resolve({ ok: true, json: async () => data }); }

async function main() {
    inputSource.value = 'https://www.uukanshu.cc/book/1/';
    let pending = api.refreshBookMetadata();
    reply(0, info('Source A', 'Author A'));
    await pending;
    assert.equal(form.elements.title.value, 'Source A');
    assert.equal(form.elements.author.value, 'Author A');
    assert.equal(profile.hidden, false);
    assert.equal(nodes['book-original-title'].textContent, 'Source A');
    assert.match(nodes['book-exported-chapters'].textContent, /^7 /);
    assert.equal(nodes['book-identifier'].textContent, 'urn:uuid:fixture');
    assert.equal(nodes['book-model'].textContent, 'deepseek-flash');

    form.elements.title.value = 'Manual title';
    form.elements.title.listeners.input();
    inputSource.value = 'https://www.uukanshu.cc/book/2/';
    pending = api.refreshBookMetadata();
    reply(1, info('Source B', 'Author B'));
    await pending;
    assert.equal(form.elements.title.value, 'Manual title', 'Do not overwrite an edited title');
    assert.equal(form.elements.author.value, 'Author B', 'Replace the automatically filled author for a new book');

    form.elements.title.value = '';
    form.elements.title.listeners.input();
    inputSource.value = 'https://www.uukanshu.cc/book/3/';
    const old = api.refreshBookMetadata();
    inputSource.value = 'https://www.uukanshu.cc/book/4/';
    pending = api.refreshBookMetadata();
    reply(3, info('Source D', 'Author D'));
    await pending;
    reply(2, info('Source C', 'Author C'));
    await old;
    assert.equal(form.elements.title.value, 'Source D', 'Ignore an old source response');
    assert.match(status.textContent, /Source D/, 'Keep the current source description');

    inputSource.value = 'https://www.uukanshu.cc/book/5/';
    pending = api.refreshBookMetadata();
    form.elements.title.value = 'Typed while loading';
    form.elements.title.listeners.input();
    reply(4, info('Source E', 'Author E'));
    await pending;
    assert.equal(form.elements.title.value, 'Typed while loading');
    inputSource.value = '';
    await api.refreshBookMetadata();
    assert.equal(status.textContent, '');
    assert.equal(profile.hidden, true);
    assert.equal(form.elements.title.value, 'Typed while loading');
    console.log('PASS: metadata autofill, manual edits, source changes and stale responses');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
