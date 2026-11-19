// Independent GB SHIRT schema excerpt captured from the native UK editor:
// research-e2e-20261117/native-auto-GB-schema-response-38.json, schema hash
// 21fe010c36a58982. Its amount key differs from the US schema's `value`.
export const gbShirtListPrice={
 type:'array',items:{type:'object',required:['currency','value_with_tax'],properties:{
  currency:{enum:['GBP'],type:'string',title:'List Price Currency',hidden:true,editable:false,examples:['GBP'],enumNames:['GBP'],description:'Select the corresponding currency'},
  marketplace_id:{$ref:'#/$defs/marketplace_id'},
  value_with_tax:{type:'number',title:'List Price with Tax',hidden:false,minimum:0,editable:true,examples:['69'],maxLength:20,multipleOf:0.01,
   description:"Provide the list price for the product including the tax. List price is often referred to as the manufacturer's suggested retail price (MSRP) or the recommended retail price (RRP) set by the manufacturer and provided by the manufacturer, supplier, or seller. This is not the offering or cost price. If you are unable to provide a value, enter 0."}
 },additionalProperties:false},title:'List Price',examples:['64 USD, 69 GBP, 98 EUR'],minItems:1,selectors:['marketplace_id','currency'],
 description:'Provide the list price for the product. List Price is the suggested retail price of a product as provided by a manufacturer, supplier, or seller. This is not the offering or cost price.',maxUniqueItems:1,minUniqueItems:1
};
