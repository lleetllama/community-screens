const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');

test('clock ticks offline and rolls over midnight in the facility timezone', async () => {
  let elapsed = 0;
  const elements = new Map();
  const timers = new Map();
  const context = vm.createContext({
    window: {
      SIGNAGE_SLUG: 'lobby',
      SIGNAGE_TIME: '2026-10-22T23:59:59-04:00',
      SIGNAGE_TIMEZONE: 'America/New_York',
    },
    document: {
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, { textContent: '' });
        return elements.get(id);
      },
      addEventListener() {},
    },
    performance: { now: () => elapsed },
    fetch: async () => { throw new Error('offline'); },
    setInterval: (callback, interval) => timers.set(interval, callback),
    requestAnimationFrame: () => 1,
    cancelAnimationFrame() {},
    ResizeObserver: class { observe() {} },
    Intl, Date,
  });
  vm.runInContext(fs.readFileSync('static/display.js', 'utf8'), context);
  assert.equal(elements.get('clock').textContent, '11:59:59 PM');
  await new Promise(resolve => setImmediate(resolve));
  assert.match(elements.get('updateStatus').textContent, /Reconnecting/);
  elapsed = 2000;
  timers.get(1000)();
  assert.equal(elements.get('clock').textContent, '12:00:01 AM');
  assert.equal(elements.get('todayDate').textContent, 'Friday, October 23, 2026');
  // A successful refresh must use the latest per-display empty message.
  const list = elements.get('eventList');
  list.replaceChildren = () => { list.children = []; };
  list.append = child => list.children.push(child);
  context.document.createElement = () => ({});
  let emptyMessage = 'Please check back tomorrow.';
  context.fetch = async () => ({
    ok: true,
    json: async () => ({
      time: '2026-10-23T00:00:01-04:00', events: [],
      display: { heading: 'Community news', empty_message: emptyMessage },
    }),
  });
  await vm.runInContext('refresh()', context);
  assert.equal(list.children[0].textContent, emptyMessage);
  emptyMessage = 'Enjoy your weekend!';
  await vm.runInContext('refresh()', context);
  assert.equal(list.children[0].textContent, emptyMessage);
  assert.equal(elements.get('updateStatus').textContent, 'Live schedule');
});
