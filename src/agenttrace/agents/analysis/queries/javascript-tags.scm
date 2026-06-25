(function_declaration
  name: (identifier) @name.definition.function)

(class_declaration
  name: (identifier) @name.definition.class)

(method_definition
  name: (property_identifier) @name.definition.method)

(lexical_declaration
  name: (identifier) @name.definition.const)

(call_expression
  function: [
    (identifier) @name.reference.call
    (member_expression
      property: (property_identifier) @name.reference.call)
  ])
