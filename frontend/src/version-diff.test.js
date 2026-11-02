import test from 'node:test'
import assert from 'node:assert/strict'
import { lineDiff } from './version-diff.js'
test('preserves common lines and identifies additions/deletions', () => {
  const result = lineDiff('案例甲\n旧结构\n结尾', '案例甲\n三步清单\n结尾')
  assert.deepEqual(result, [
    { type: 'same', text: '案例甲' }, { type: 'removed', text: '旧结构' },
    { type: 'added', text: '三步清单' }, { type: 'same', text: '结尾' }])
  assert.equal(result.filter(x => x.type !== 'added').map(x => x.text).join('\n'), '案例甲\n旧结构\n结尾')
  assert.equal(result.filter(x => x.type !== 'removed').map(x => x.text).join('\n'), '案例甲\n三步清单\n结尾')
})
