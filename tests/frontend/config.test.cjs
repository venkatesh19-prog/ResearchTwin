const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../frontend/frontend-config.js'), 'utf8');

for (const hostname of ['localhost', '127.0.0.1', '[::1]']) {
    test(`local development on ${hostname} uses the local API`, () => {
        const window = { location: { hostname } };
        vm.runInNewContext(source, { window });
        assert.equal(window.RESEARCHTWIN_API_BASE, 'http://127.0.0.1:8000');
    });
}

test('explicit API configuration is preserved', () => {
    const window = { location: { hostname: 'localhost' }, RESEARCHTWIN_API_BASE: 'http://127.0.0.1:8799' };
    vm.runInNewContext(source, { window });
    assert.equal(window.RESEARCHTWIN_API_BASE, 'http://127.0.0.1:8799');
});
