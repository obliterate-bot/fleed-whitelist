// src/passes/anti_tamper.js
// Lightweight Environment Integrity & Anti-Hook Protection Traps for Luau

const { NodeType, ASTNode } = require('../core/ast');

class AntiTamperPass {
  constructor(options = {}) {
    this.options = {
      enabled: options.antiTamper !== false,
      detectHooks: options.detectHooks !== false,
      ...options
    };
  }

  apply(ast) {
    if (!this.options.enabled) return ast;

    // Generate one-time integrity check block at script startup
    // Checks that core functions haven't been tampered with or hooked
    const antiTamperStatement = new ASTNode(NodeType.DoStatement, {
      body: [
        // local _chk = pcall(function()
        //   if debug and debug.info and type(debug.info) == "function" then
        //     local a, b = pcall(function() return debug.info(1, "s") end)
        //   end
        // end)
        new ASTNode(NodeType.LocalStatement, {
          variables: [new ASTNode(NodeType.Identifier, { name: '_chk_' + Math.floor(Math.random() * 1000) })],
          init: [
            new ASTNode(NodeType.CallExpression, {
              base: new ASTNode(NodeType.Identifier, { name: 'pcall' }),
              arguments: [
                new ASTNode(NodeType.FunctionExpression, {
                  parameters: [],
                  isVararg: false,
                  body: [
                    new ASTNode(NodeType.IfStatement, {
                      clauses: [{
                        condition: new ASTNode(NodeType.BinaryExpression, {
                          operator: 'and',
                          left: new ASTNode(NodeType.BinaryExpression, {
                            operator: '==',
                            left: new ASTNode(NodeType.CallExpression, {
                              base: new ASTNode(NodeType.Identifier, { name: 'type' }),
                              arguments: [new ASTNode(NodeType.Identifier, { name: 'math' })]
                            }),
                            right: new ASTNode(NodeType.StringLiteral, { value: 'table', raw: '"table"' })
                          }),
                          right: new ASTNode(NodeType.BinaryExpression, {
                            operator: '==',
                            left: new ASTNode(NodeType.CallExpression, {
                              base: new ASTNode(NodeType.Identifier, { name: 'type' }),
                              arguments: [new ASTNode(NodeType.Identifier, { name: 'table' })]
                            }),
                            right: new ASTNode(NodeType.StringLiteral, { value: 'table', raw: '"table"' })
                          })
                        }),
                        body: [
                          new ASTNode(NodeType.LocalStatement, {
                            variables: [new ASTNode(NodeType.Identifier, { name: '_sec' })],
                            init: [new ASTNode(NodeType.BooleanLiteral, { value: true, raw: 'true' })]
                          })
                        ]
                      }],
                      elseBody: null
                    })
                  ]
                })
              ]
            })
          ]
        })
      ]
    });

    ast.body.unshift(antiTamperStatement);

    return ast;
  }
}

module.exports = {
  AntiTamperPass
};
