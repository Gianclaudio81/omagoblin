const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../Main.qml`, 'utf8');
// Execute the actual QML JavaScript functions, without a desktop session.
const functions = source.match(/^  function [^\n]*\{\n[\s\S]*?^  }/gm).join('\n');
function context() {
  const ctx = vm.createContext({aggregateData: {}, syncRevision: 0, syncStatusText: '', syncEnabled: true, syncDir: '/sync', Quickshell: {env: () => ''}});
  ctx.root = ctx;
  vm.runInContext(functions, ctx);
  return ctx;
}
test('valid snapshots preserve additive and account aggregation', () => {
  const ctx = context();
  ctx.parseSyncScanOutput(JSON.stringify({snapshots: ['a', 'b'].map(deviceId => ({deviceId, providers: {codex: {todayPrompts: 3}, fireworks: {scope: 'account', todayTotalTokens: 10}}})), rejected: 0, limited: false}));
  assert.equal(ctx.aggregateData.deviceCount, 2);
  assert.equal(ctx.aggregateData.providers.codex.todayPrompts, 6);
  assert.equal(ctx.aggregateData.providers.fireworks.todayTotalTokens, 10);
  assert.equal(ctx.syncStatusText, '');
});
test('invalid, oversized and excessive envelopes retain previous aggregate', () => {
  const ctx = context();
  const previous = ctx.aggregateData;
  for (const output of ['{', ' '.repeat(2 * 1024 * 1024 + 1), JSON.stringify({snapshots: Array(65).fill({providers: {}})})]) {
    ctx.parseSyncScanOutput(output);
    assert.equal(ctx.aggregateData, previous);
    assert.equal(ctx.syncStatusText, 'Usage sync scan failed');
  }
});
test('skipped snapshots are visible; disabled sync ignores late output', () => {
  const ctx = context();
  ctx.parseSyncScanOutput('{"snapshots":[],"rejected":1,"limited":false}');
  assert.match(ctx.syncStatusText, /skipped/);
  const previous = ctx.aggregateData;
  ctx.syncEnabled = false;
  ctx.parseSyncScanOutput('{"snapshots":[]}');
  assert.equal(ctx.aggregateData, previous);
});
