const fs = require('fs');
const { Parser } = require('../src/core/parser');
const { ScopeAnalyzer } = require('../src/core/scope');
const { NodeType, ASTNode, walk, cloneNode } = require('../src/core/ast');
const { StringCryptoPass } = require('../src/passes/string_crypto');
const { Generator } = require('../src/core/generator');

const code = `
local Config = {
  Enabled = true,
  SilentAim = false,
  FOV = 120,
  Color = Color3.fromRGB(255, 0, 0)
}

function test(player)
  if player:FindFirstChild("HumanoidRootPart") then
    local pos = player.Character.HumanoidRootPart.Position
    print("Found position:", pos, UDim2.new(1, 0, 1, 0))
    writefile("log.txt", tostring(pos))
  end
end
`;

const p = new Parser(code);
const ast = p.parse();

// 1. TableKeyString -> TableKey
walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.TableKeyString) {
      const keyName = node.key.name;
      node.type = NodeType.TableKey;
      node.key = new ASTNode(NodeType.StringLiteral, { value: keyName, raw: `"${keyName}"` });
    }
  }
});

// 2. MemberExpression '.' -> IndexExpression
walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.MemberExpression && node.indexer === '.') {
      const propName = node.identifier.name;
      node.type = NodeType.IndexExpression;
      node.index = new ASTNode(NodeType.StringLiteral, { value: propName, raw: `"${propName}"` });
      delete node.identifier;
      delete node.indexer;
    }
  }
});

// 3. Method call ':' on simple identifiers -> base[method](base, ...)
walk(ast, {
  enter: (node) => {
    if (node.type === NodeType.CallExpression && node.base && node.base.type === NodeType.MemberExpression && node.base.indexer === ':') {
      if (node.base.base && node.base.base.type === NodeType.Identifier) {
        const methodName = node.base.identifier.name;
        const targetIdent = node.base.base;
        node.base = new ASTNode(NodeType.IndexExpression, {
          base: targetIdent,
          index: new ASTNode(NodeType.StringLiteral, { value: methodName, raw: `"${methodName}"` })
        });
        node.arguments.unshift(cloneNode(targetIdent));
      }
    }
  }
});

// 4. Scope analysis for global variable indirection
const scopeAnalyzer = new ScopeAnalyzer(ast);
scopeAnalyzer.analyze();

const RESERVED_GLOBALS = new Set(['_ENV', '_G', 'getfenv', 'buffer', 'bit32', 'pcall', 'type', 'math', 'table', 'string', 'self', '_S']);

walk(ast, {
  enter: (node, parent) => {
    if (node.type === NodeType.Identifier && node.isGlobal) {
      if (!RESERVED_GLOBALS.has(node.name)) {
        // Replace with _ENV["GlobalName"]
        const globalName = node.name;
        node.type = NodeType.IndexExpression;
        node.base = new ASTNode(NodeType.Identifier, { name: '_ENV' });
        node.index = new ASTNode(NodeType.StringLiteral, { value: globalName, raw: `"${globalName}"` });
        delete node.name;
        delete node.isGlobal;
      }
    }
  }
});

// Prepend local _ENV = (getfenv and getfenv()) or _G
ast.body.unshift(new ASTNode(NodeType.LocalStatement, {
  variables: [new ASTNode(NodeType.Identifier, { name: '_ENV' })],
  init: [
    new ASTNode(NodeType.LogicalExpression, {
      operator: 'or',
      left: new ASTNode(NodeType.LogicalExpression, {
        operator: 'and',
        left: new ASTNode(NodeType.Identifier, { name: 'getfenv' }),
        right: new ASTNode(NodeType.CallExpression, {
          base: new ASTNode(NodeType.Identifier, { name: 'getfenv' }),
          arguments: []
        })
      }),
      right: new ASTNode(NodeType.Identifier, { name: '_G' })
    })
  ]
}));

// 5. String Cryptography
const cryptoPass = new StringCryptoPass();
cryptoPass.apply(ast);

const gen = new Generator({ minify: true });
const output = gen.generate(ast);
console.log('--- Obfuscated Code ---');
console.log(output);
