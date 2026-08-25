// src/passes/member_indirection.js
// Member, Table Key, Method, and Global Variable Indirection Engine

const { NodeType, ASTNode, walk, cloneNode } = require('../core/ast');
const { ScopeAnalyzer } = require('../core/scope');

const FASTCALL_GLOBALS = [
  'math.sin', 'math.cos', 'math.floor', 'math.ceil', 'math.sqrt', 'math.abs', 'math.max', 'math.min', 'math.rad', 'math.deg',
  'table.insert', 'table.remove', 'table.concat', 'table.find', 'table.sort',
  'string.byte', 'string.char', 'string.sub', 'string.len', 'string.find', 'string.format',
  'bit32.bxor', 'bit32.band', 'bit32.bor', 'bit32.bnot', 'bit32.lshift', 'bit32.rshift',
  'buffer.create', 'buffer.readu8', 'buffer.writeu8', 'buffer.readstring', 'buffer.writestring'
];

const RESERVED_GLOBALS = new Set([
  '_ENV', '_G', 'getfenv', 'buffer', 'bit32', 'pcall', 'type', 'math', 'table', 'string', 'self', '_S', 'true', 'false', 'nil'
]);

class MemberIndirectionPass {
  constructor(options = {}) {
    this.options = {
      localizeGlobals: options.localizeGlobals !== false,
      indirectMembers: options.indirectMembers !== false,
      indirectTableKeys: options.indirectTableKeys !== false,
      indirectMethods: options.indirectMethods !== false,
      indirectGlobals: options.indirectGlobals !== false,
      ...options
    };
  }

  apply(ast) {
    // 1. Function declaration indirection FIRST: function obj.prop(...) -> obj["prop"] = function(...)
    //                                              function obj:method(...) -> obj["method"] = function(self, ...)
    walk(ast, {
      enter: (node) => {
        if (node.type === NodeType.FunctionDeclaration && node.identifier && node.identifier.type !== NodeType.Identifier) {
          const isMethod = node.isMethod || (node.identifier.type === NodeType.MemberExpression && node.identifier.indexer === ':');
          let targetVar = null;

          if (node.identifier.type === NodeType.MemberExpression) {
            const methodName = node.identifier.identifier.name;
            const targetBase = node.identifier.base;
            targetVar = new ASTNode(NodeType.IndexExpression, {
              base: targetBase,
              index: new ASTNode(NodeType.StringLiteral, { value: methodName, raw: `"${methodName}"` })
            });
          } else {
            targetVar = node.identifier;
          }

          const params = [...node.parameters];
          if (isMethod) {
            params.unshift(new ASTNode(NodeType.Identifier, { name: 'self' }));
          }

          node.type = NodeType.AssignmentStatement;
          node.variables = [targetVar];
          node.init = [
            new ASTNode(NodeType.FunctionExpression, {
              parameters: params,
              isVararg: node.isVararg,
              body: node.body
            })
          ];
          delete node.identifier;
          delete node.parameters;
          delete node.isMethod;
          delete node.body;
          delete node.isVararg;
        }
      }
    });

    // 2. Table Key Indirection: { Key = value } -> { ["Key"] = value }
    if (this.options.indirectTableKeys) {
      walk(ast, {
        enter: (node) => {
          if (node.type === NodeType.TableKeyString) {
            const keyName = node.key.name;
            node.type = NodeType.TableKey;
            node.key = new ASTNode(NodeType.StringLiteral, { value: keyName, raw: `"${keyName}"` });
          }
        }
      });
    }

    // 3. Member expression indirection: a.b -> a["b"]
    if (this.options.indirectMembers) {
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
    }

    // 4. Method call indirection on all method calls: target:Method(args) -> target["Method"](target, args)
    if (this.options.indirectMethods) {
      walk(ast, {
        enter: (node) => {
          if (node.type === NodeType.CallExpression && node.base && node.base.type === NodeType.MemberExpression && node.base.indexer === ':') {
            const methodName = node.base.identifier.name;
            const targetNode = node.base.base;
            node.base = new ASTNode(NodeType.IndexExpression, {
              base: targetNode,
              index: new ASTNode(NodeType.StringLiteral, { value: methodName, raw: `"${methodName}"` })
            });
            node.arguments.unshift(cloneNode(targetNode));
          }
        }
      });
    }

    // 5. Global variable indirection: GlobalVar -> _ENV["GlobalVar"]
    if (this.options.indirectGlobals) {
      const scopeAnalyzer = new ScopeAnalyzer(ast);
      scopeAnalyzer.analyze();

      let usedEnv = false;
      walk(ast, {
        enter: (node, parent) => {
          if (node.type === NodeType.Identifier && node.isGlobal) {
            if (!RESERVED_GLOBALS.has(node.name)) {
              const globalName = node.name;
              node.type = NodeType.IndexExpression;
              node.base = new ASTNode(NodeType.Identifier, { name: '_ENV' });
              node.index = new ASTNode(NodeType.StringLiteral, { value: globalName, raw: `"${globalName}"` });
              delete node.name;
              delete node.isGlobal;
              usedEnv = true;
            }
          }
        }
      });

      if (usedEnv) {
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
      }
    }

    // 6. Global fastcall localization
    if (this.options.localizeGlobals) {
      this.localizeFastcallGlobals(ast);
    }

    return ast;
  }

  localizeFastcallGlobals(ast) {
    const usedGlobals = new Map();

    walk(ast, {
      enter: (node) => {
        if (node.type === NodeType.IndexExpression && node.base && node.base.type === NodeType.Identifier && node.index && node.index.type === NodeType.StringLiteral) {
          const globalKey = `${node.base.name}.${node.index.value}`;
          if (FASTCALL_GLOBALS.includes(globalKey)) {
            if (!usedGlobals.has(globalKey)) {
              const aliasName = `_g_${node.base.name}_${node.index.value}_${Math.floor(Math.random() * 1000)}`;
              usedGlobals.set(globalKey, aliasName);
            }
            const alias = usedGlobals.get(globalKey);
            node.type = NodeType.Identifier;
            node.name = alias;
            delete node.base;
            delete node.index;
          }
        }
      }
    });

    if (usedGlobals.size === 0) return;

    const localStatements = [];
    for (const [globalKey, aliasName] of usedGlobals.entries()) {
      const [baseName, propName] = globalKey.split('.');
      localStatements.push(new ASTNode(NodeType.LocalStatement, {
        variables: [new ASTNode(NodeType.Identifier, { name: aliasName })],
        init: [
          new ASTNode(NodeType.IndexExpression, {
            base: new ASTNode(NodeType.Identifier, { name: baseName }),
            index: new ASTNode(NodeType.StringLiteral, { value: propName, raw: `"${propName}"` })
          })
        ]
      }));
    }

    ast.body.unshift(...localStatements);
  }
}

module.exports = {
  MemberIndirectionPass
};
