if(CMAKE_SYSTEM_PROCESSOR MATCHES "(^arm)|(^aarch64)")
  add_library(ldpc_decoder_neon STATIC ldpc_decoder_neon.cc)
  # -mfpu=neon is only needed for 32-bit ARM Linux, not for aarch64 or macOS
  if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "(^aarch64)")
    if(NOT APPLE)
      target_compile_options(ldpc_decoder_neon PRIVATE -mfpu=neon)
    endif()
  endif()
  list(APPEND LDPC_LIBS ldpc_decoder_neon)
endif()

if(CMAKE_SYSTEM_PROCESSOR MATCHES "(x86_64)|(AMD64|amd64)|(^i.86$)")
  add_library(ldpc_decoder_avx2 STATIC ldpc_decoder_avx2.cc)
  add_library(ldpc_decoder_sse41 STATIC ldpc_decoder_sse41.cc)
  target_compile_options(ldpc_decoder_avx2 PRIVATE -mavx2)
  target_compile_options(ldpc_decoder_sse41 PRIVATE -msse4.1)
  list(APPEND LDPC_LIBS ldpc_decoder_avx2)
  list(APPEND LDPC_LIBS ldpc_decoder_sse41)
endif()

add_library(ldpc_decoder_generic STATIC ldpc_decoder_generic.cc)
list(APPEND LDPC_LIBS ldpc_decoder_generic)

foreach(LDPC_LIB ${LDPC_LIBS})
  set_property(TARGET ${LDPC_LIB} PROPERTY POSITION_INDEPENDENT_CODE ON)
endforeach()

set(LDPC_LIBS ${LDPC_LIBS} PARENT_SCOPE)
