const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../Main.qml`, 'utf8');
const functions = source.match(/^  function [^\n]*\{\n[\s\S]*?^  }/gm).join('\n');
function context() {
  const ctx = vm.createContext({agents: [], dataRevision: 0, console: {warn() {}}});
  ctx.root = ctx;
  vm.runInContext(functions, ctx);
  ctx.changes = 0;
  ctx.recordsChanged = () => { ctx.changes++; };
  return ctx;
}
test('helper envelope becomes agent records', () => {
  const ctx = context();
  ctx.applyAgentRecords(JSON.stringify({records: [{agentId: 'codex', record: {id: 'codex'}}, {agentId: 'x', record: []}], rejected: 1}));
  assert.equal(ctx.agents.length, 2);
  assert.equal(ctx.agents[0].record.id, 'codex');
  assert.equal(ctx.agents[1].record, null);
  assert.equal(ctx.changes, 1);
  ctx.applyAgentRecords(JSON.stringify({records: [{agentId: 'codex', record: {id: 'codex'}}, {agentId: 'x', record: []}]}));
  assert.equal(ctx.changes, 1);
});
test('unreadable output keeps previous records', () => {
  const ctx = context();
  ctx.applyAgentRecords(JSON.stringify({records: [{agentId: 'codex', record: {id: 'codex'}}]}));
  const previous = ctx.agents;
  for (const output of ['{', '', '{"records":null}']) ctx.applyAgentRecords(output);
  assert.equal(ctx.agents, previous);
});
