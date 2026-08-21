const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ScopeAnalyzer } = require('../src/core/scope');
const { NodeType } = require('../src/core/ast');

const s = fs.readFileSync('./goldeneaglehub.luau', 'utf8');
const p = new Parser(s);
const ast = p.parse();

const analyzer = new ScopeAnalyzer(ast);
const { rootScope, allScopes } = analyzer.analyze();

console.log('Root declarations has Compat:', rootScope.declarations.has('Compat'));
const sym = rootScope.declarations.get('Compat');
if (sym) {
  console.log('Compat references count:', sym.references.length);
  for (let i = 0; i < sym.references.length; i++) {
    console.log(`  ref ${i}: line ${sym.references[i].line || '?'}`);
  }
}
