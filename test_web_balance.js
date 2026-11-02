// Run with: node test_web_balance.js
'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(process.env.BALANCE_TEST_SOURCE || 'web/app.js', 'utf8');
const start = source.indexOf('    let lastKeyBalance = null;');
const end = source.indexOf('    async function refreshEstimate()', start);
assert.ok(start >= 0 && end > start, 'Balance functions must be present');

const requests = [];
const intervals = [];
const events = {};
const apiKeyInput = { value: 'key-a' };
const label = () => ({ textContent: '', hidden: true });
const context = {
    apiKeyInput, AbortController, URLSearchParams,
    estimateBalanceRow: label(), estimateBalance: label(), estimateBalanceDetail: label(),
    document: { hidden: false, addEventListener: (name, fn) => { events[name] = fn; } },
    window: { addEventListener: (name, fn) => { events[name] = fn; } },
    setInterval: (fn, delay) => { intervals.push({ fn, delay }); },
    fetch: (url, options) => new Promise((resolve, reject) => {
        requests.push({ url, options, resolve, reject });
    }),
};
context.postForm = (url, fields) => context.fetch(url, { body: new URLSearchParams(fields) });
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
const api = vm.runInContext('({ refreshKeyBalance, formatUsd })', context);

function reply(index, balance) {
    requests[index].resolve({
        ok: true,
        json: async () => ({ available: true, is_available: true, balance_infos: [{
            currency: 'USD', total_balance: balance, granted_balance: '0.00', topped_up_balance: balance,
        }] }),
    });
}

async function main() {
    assert.equal(api.formatUsd(0), '$0.00');
    assert.equal(api.formatUsd(0.001), '< $0.01', 'A positive tiny estimate must not look free');
    assert.equal(api.formatUsd(1.14), '$1.14');
    assert.equal(intervals.length, 1, 'Balance must refresh periodically');
    assert.equal(intervals[0].delay, 30000);
    assert.equal(typeof events.visibilitychange, 'function');
    assert.equal(typeof events.focus, 'function');

    let pending = api.refreshKeyBalance('key-a');
    reply(0, '1.14');
    await pending;
    assert.equal(context.estimateBalance.textContent, '1.14 USD');

    pending = api.refreshKeyBalance('key-a');
    assert.notEqual(context.estimateBalance.textContent, '1.14 USD', 'Old amount must not look current while refreshing');
    reply(1, '0.98');
    await pending;
    assert.equal(context.estimateBalance.textContent, '0.98 USD');

    const oldRequest = api.refreshKeyBalance('key-a');
    apiKeyInput.value = 'key-b';
    const newRequest = api.refreshKeyBalance('key-b');
    reply(3, '7.25');
    await newRequest;
    reply(2, '1.14');
    await oldRequest;
    assert.equal(context.estimateBalance.textContent, '7.25 USD', 'Old key response must not overwrite new key balance');

    pending = api.refreshKeyBalance('key-b');
    const count = requests.length;
    await api.refreshKeyBalance('key-b');
    assert.equal(requests.length, count, 'Concurrent refreshes for one key must share the request');
    requests[count - 1].reject(new Error('offline'));
    await pending;
    assert.notEqual(context.estimateBalance.textContent, '7.25 USD');
    assert.match(context.estimateBalanceDetail.textContent, /offline/);

    context.document.hidden = true;
    intervals[0].fn();
    assert.equal(requests.length, count, 'Hidden tabs must not poll');
    context.document.hidden = false;
    events.focus();
    assert.equal(requests.length, count + 1);
    const signal = requests[count].options.signal;
    apiKeyInput.value = '';
    await api.refreshKeyBalance('');
    assert.equal(signal.aborted, true);
    reply(count, '999');
    await new Promise(resolve => setImmediate(resolve));
    assert.notEqual(context.estimateBalance.textContent, '999.00 USD');
    console.log('PASS: balance freshness, key races, request deduplication, network errors and empty key');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
