bits 64

extern puts
global foo

section .data

message:
  db 'foo() called', 0

section .text

foo:
  nop
  push rbp
  mov rbp, rsp
  lea rdi, [rel message]
  %ifdef USE_PLT
    call puts wrt ..plt
  %else
    call puts
  %endif
  pop rbp
  ret

global foo_frame

foo_frame:
  push rbp
  mov rbp, rsp
  lea rax, [rbp - 16]
  mov dword [rax], 42
  mov eax, [rax]
  pop rbp
  ret
