path "secret/data/medgenome/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

path "secret/metadata/medgenome/*" {
  capabilities = ["list", "read", "delete"]
}
