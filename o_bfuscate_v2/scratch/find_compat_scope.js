const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ScopeAnalyzer } = require('../src/core/scope');
const { NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

const analyzer = new ScopeAnalyzer(ast);
const { rootScope, allScopes } = analyzer.analyze();

for (let i = 0; i < allScopes.length; i++) {
  const sc = allScopes[i];
  if (sc.declarations.has('Compat')) {
    console.log(`Scope #${i} (isFunction: ${sc.isFunction}) has Compat with ${sc.declarations.get('Compat').references.length} refs`);
  }
}
