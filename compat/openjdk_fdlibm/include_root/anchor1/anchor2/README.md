# fdlibm relative-include anchor

This regular directory depth lets OpenJDK's
`../../external/fdlibm/fdlibm.h` include resolve into the sibling
`include_root/external/fdlibm` forwarding header. It replaces the former
filesystem aliases and is required on both case-sensitive and
case-insensitive source projections.
