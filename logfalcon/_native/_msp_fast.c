/*
 * _msp_fast — CPython C extension for MSP protocol hot paths.
 *
 * Accelerates:
 *   1. crc8_xor(data) -> int
 *   2. crc8_dvb_s2(data, initial=0) -> int
 *   3. msp_decode(data, state_capsule) -> list[tuple]
 *   4. huffman_decode(in_buf, char_count) -> bytes
 */

#define PY_SSIZE_T_CLEAN
#include <Python.h>

/* ------------------------------------------------------------------ */
/* CRC8-DVB-S2 lookup table (polynomial 0xD5)                         */
/* ------------------------------------------------------------------ */

static const unsigned char crc8_dvb_s2_table[256] = {
    0x00, 0xD5, 0x7F, 0xAA, 0xFE, 0x2B, 0x81, 0x54,
    0x29, 0xFC, 0x56, 0x83, 0xD7, 0x02, 0xA8, 0x7D,
    0x52, 0x87, 0x2D, 0xF8, 0xAC, 0x79, 0xD3, 0x06,
    0x7B, 0xAE, 0x04, 0xD1, 0x85, 0x50, 0xFA, 0x2F,
    0xA4, 0x71, 0xDB, 0x0E, 0x5A, 0x8F, 0x25, 0xF0,
    0x8D, 0x58, 0xF2, 0x27, 0x73, 0xA6, 0x0C, 0xD9,
    0xF6, 0x23, 0x89, 0x5C, 0x08, 0xDD, 0x77, 0xA2,
    0xDF, 0x0A, 0xA0, 0x75, 0x21, 0xF4, 0x5E, 0x8B,
    0x9D, 0x48, 0xE2, 0x37, 0x63, 0xB6, 0x1C, 0xC9,
    0xB4, 0x61, 0xCB, 0x1E, 0x4A, 0x9F, 0x35, 0xE0,
    0xCF, 0x1A, 0xB0, 0x65, 0x31, 0xE4, 0x4E, 0x9B,
    0xE6, 0x33, 0x99, 0x4C, 0x18, 0xCD, 0x67, 0xB2,
    0x39, 0xEC, 0x46, 0x93, 0xC7, 0x12, 0xB8, 0x6D,
    0x10, 0xC5, 0x6F, 0xBA, 0xEE, 0x3B, 0x91, 0x44,
    0x6B, 0xBE, 0x14, 0xC1, 0x95, 0x40, 0xEA, 0x3F,
    0x42, 0x97, 0x3D, 0xE8, 0xBC, 0x69, 0xC3, 0x16,
    0xEF, 0x3A, 0x90, 0x45, 0x11, 0xC4, 0x6E, 0xBB,
    0xC6, 0x13, 0xB9, 0x6C, 0x38, 0xED, 0x47, 0x92,
    0xBD, 0x68, 0xC2, 0x17, 0x43, 0x96, 0x3C, 0xE9,
    0x94, 0x41, 0xEB, 0x3E, 0x6A, 0xBF, 0x15, 0xC0,
    0x4B, 0x9E, 0x34, 0xE1, 0xB5, 0x60, 0xCA, 0x1F,
    0x62, 0xB7, 0x1D, 0xC8, 0x9C, 0x49, 0xE3, 0x36,
    0x19, 0xCC, 0x66, 0xB3, 0xE7, 0x32, 0x98, 0x4D,
    0x30, 0xE5, 0x4F, 0x9A, 0xCE, 0x1B, 0xB1, 0x64,
    0x72, 0xA7, 0x0D, 0xD8, 0x8C, 0x59, 0xF3, 0x26,
    0x5B, 0x8E, 0x24, 0xF1, 0xA5, 0x70, 0xDA, 0x0F,
    0x20, 0xF5, 0x5F, 0x8A, 0xDE, 0x0B, 0xA1, 0x74,
    0x09, 0xDC, 0x76, 0xA3, 0xF7, 0x22, 0x88, 0x5D,
    0xD6, 0x03, 0xA9, 0x7C, 0x28, 0xFD, 0x57, 0x82,
    0xFF, 0x2A, 0x80, 0x55, 0x01, 0xD4, 0x7E, 0xAB,
    0x84, 0x51, 0xFB, 0x2E, 0x7A, 0xAF, 0x05, 0xD0,
    0xAD, 0x78, 0xD2, 0x07, 0x53, 0x86, 0x2C, 0xF9,
};

/* ------------------------------------------------------------------ */
/* crc8_xor(data) -> int                                              */
/* ------------------------------------------------------------------ */

static PyObject *
msp_crc8_xor(PyObject *self, PyObject *args)
{
    Py_buffer buf;
    if (!PyArg_ParseTuple(args, "y*", &buf))
        return NULL;

    const unsigned char *p = (const unsigned char *)buf.buf;
    Py_ssize_t len = buf.len;
    unsigned int result = 0;
    for (Py_ssize_t i = 0; i < len; i++)
        result ^= p[i];

    PyBuffer_Release(&buf);
    return PyLong_FromUnsignedLong(result & 0xFF);
}

/* ------------------------------------------------------------------ */
/* crc8_dvb_s2(data, initial=0) -> int                                */
/* ------------------------------------------------------------------ */

static PyObject *
msp_crc8_dvb_s2(PyObject *self, PyObject *args)
{
    Py_buffer buf;
    unsigned int initial = 0;
    if (!PyArg_ParseTuple(args, "y*|I", &buf, &initial))
        return NULL;

    const unsigned char *p = (const unsigned char *)buf.buf;
    Py_ssize_t len = buf.len;
    unsigned int crc = initial & 0xFF;
    for (Py_ssize_t i = 0; i < len; i++)
        crc = crc8_dvb_s2_table[crc ^ p[i]];

    PyBuffer_Release(&buf);
    return PyLong_FromUnsignedLong(crc);
}

/* ------------------------------------------------------------------ */
/* MSP frame decoder                                                  */
/* ------------------------------------------------------------------ */

enum msp_state {
    MSP_IDLE = 1, MSP_PROTO_V1_M, MSP_PROTO_DIRECTION,
    MSP_V1_LEN, MSP_V1_CODE, MSP_V1_PAYLOAD, MSP_V1_CHECKSUM,
    MSP_V2_FLAG, MSP_V2_CODE_LO, MSP_V2_CODE_HI,
    MSP_V2_LEN_LO, MSP_V2_LEN_HI, MSP_V2_PAYLOAD, MSP_V2_CHECKSUM,
};

typedef struct {
    enum msp_state state;
    int version;
    int direction;
    int code;
    int size;
    int payload_idx;
    unsigned int checksum;
    unsigned char v2_header[5];
    int v2_header_len;
    unsigned char *payload;
    int payload_cap;
} DecoderState;

static void
decoder_reset(DecoderState *ds)
{
    ds->state = MSP_IDLE;
    ds->version = 0;
    ds->direction = 0;
    ds->code = 0;
    ds->size = 0;
    ds->payload_idx = 0;
    ds->checksum = 0;
    ds->v2_header_len = 0;
}

static void
decoder_ensure_payload(DecoderState *ds, int needed)
{
    if (needed > ds->payload_cap) {
        int new_cap = needed > 256 ? needed : 256;
        unsigned char *tmp = (unsigned char *)PyMem_Realloc(ds->payload, new_cap);
        if (tmp) {
            ds->payload = tmp;
            ds->payload_cap = new_cap;
        }
    }
}

/*
 * msp_decode(data) -> list of (version, direction, code, payload_bytes)
 *
 * Stateless per call — processes a complete buffer and returns all
 * decoded frames. Internal state is maintained across calls.
 */

/* Capsule name for decoder state */
static const char *DECODER_CAPSULE = "msp_fast.DecoderState";

static void
decoder_capsule_destructor(PyObject *capsule)
{
    DecoderState *ds = (DecoderState *)PyCapsule_GetPointer(capsule, DECODER_CAPSULE);
    if (ds) {
        if (ds->payload)
            PyMem_Free(ds->payload);
        PyMem_Free(ds);
    }
}

static PyObject *
msp_decoder_new(PyObject *self, PyObject *args)
{
    DecoderState *ds = (DecoderState *)PyMem_Calloc(1, sizeof(DecoderState));
    if (!ds)
        return PyErr_NoMemory();
    ds->state = MSP_IDLE;
    ds->payload = NULL;
    ds->payload_cap = 0;
    return PyCapsule_New(ds, DECODER_CAPSULE, decoder_capsule_destructor);
}

static PyObject *
msp_decode(PyObject *self, PyObject *args)
{
    Py_buffer buf;
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "y*O", &buf, &capsule))
        return NULL;

    DecoderState *ds = (DecoderState *)PyCapsule_GetPointer(capsule, DECODER_CAPSULE);
    if (!ds) {
        PyBuffer_Release(&buf);
        return NULL;
    }

    const unsigned char *data = (const unsigned char *)buf.buf;
    Py_ssize_t len = buf.len;

    PyObject *frames = PyList_New(0);
    if (!frames) {
        PyBuffer_Release(&buf);
        return NULL;
    }

    for (Py_ssize_t i = 0; i < len; i++) {
        unsigned char b = data[i];

        switch (ds->state) {
        case MSP_IDLE:
            if (b == '$')
                ds->state = MSP_PROTO_V1_M;
            break;
        case MSP_PROTO_V1_M:
            if (b == 'M') { ds->version = 1; ds->state = MSP_PROTO_DIRECTION; }
            else if (b == 'X') { ds->version = 2; ds->state = MSP_PROTO_DIRECTION; }
            else decoder_reset(ds);
            break;
        case MSP_PROTO_DIRECTION:
            if (b == '<' || b == '>' || b == '!') {
                ds->direction = b;
                ds->state = ds->version == 1 ? MSP_V1_LEN : MSP_V2_FLAG;
            } else decoder_reset(ds);
            break;

        /* V1 */
        case MSP_V1_LEN:
            ds->size = b;
            ds->checksum = b;
            ds->payload_idx = 0;
            decoder_ensure_payload(ds, ds->size);
            ds->state = MSP_V1_CODE;
            break;
        case MSP_V1_CODE:
            ds->code = b;
            ds->checksum ^= b;
            ds->state = ds->size == 0 ? MSP_V1_CHECKSUM : MSP_V1_PAYLOAD;
            break;
        case MSP_V1_PAYLOAD:
            ds->payload[ds->payload_idx++] = b;
            ds->checksum ^= b;
            if (ds->payload_idx == ds->size)
                ds->state = MSP_V1_CHECKSUM;
            break;
        case MSP_V1_CHECKSUM:
            if (b == (ds->checksum & 0xFF)) {
                PyObject *payload_bytes = PyBytes_FromStringAndSize(
                    (const char *)ds->payload, ds->size);
                PyObject *tup = Py_BuildValue("(iiiN)",
                    ds->version, ds->direction, ds->code, payload_bytes);
                PyList_Append(frames, tup);
                Py_DECREF(tup);
            }
            decoder_reset(ds);
            break;

        /* V2 */
        case MSP_V2_FLAG:
            ds->v2_header[0] = b;
            ds->v2_header_len = 1;
            ds->state = MSP_V2_CODE_LO;
            break;
        case MSP_V2_CODE_LO:
            ds->code = b;
            ds->v2_header[ds->v2_header_len++] = b;
            ds->state = MSP_V2_CODE_HI;
            break;
        case MSP_V2_CODE_HI:
            ds->code |= b << 8;
            ds->v2_header[ds->v2_header_len++] = b;
            ds->state = MSP_V2_LEN_LO;
            break;
        case MSP_V2_LEN_LO:
            ds->size = b;
            ds->v2_header[ds->v2_header_len++] = b;
            ds->state = MSP_V2_LEN_HI;
            break;
        case MSP_V2_LEN_HI:
            ds->size |= b << 8;
            ds->v2_header[ds->v2_header_len++] = b;
            ds->payload_idx = 0;
            decoder_ensure_payload(ds, ds->size);
            ds->state = ds->size == 0 ? MSP_V2_CHECKSUM : MSP_V2_PAYLOAD;
            break;
        case MSP_V2_PAYLOAD:
            ds->payload[ds->payload_idx++] = b;
            if (ds->payload_idx == ds->size)
                ds->state = MSP_V2_CHECKSUM;
            break;
        case MSP_V2_CHECKSUM: {
            /* CRC over header + payload */
            unsigned int crc = 0;
            for (int j = 0; j < ds->v2_header_len; j++)
                crc = crc8_dvb_s2_table[crc ^ ds->v2_header[j]];
            for (int j = 0; j < ds->size; j++)
                crc = crc8_dvb_s2_table[crc ^ ds->payload[j]];
            if (b == crc) {
                PyObject *payload_bytes = PyBytes_FromStringAndSize(
                    (const char *)ds->payload, ds->size);
                PyObject *tup = Py_BuildValue("(iiiN)",
                    ds->version, ds->direction, ds->code, payload_bytes);
                PyList_Append(frames, tup);
                Py_DECREF(tup);
            }
            decoder_reset(ds);
            break;
        }
        }
    }

    PyBuffer_Release(&buf);
    return frames;
}

/* ------------------------------------------------------------------ */
/* Huffman decoder                                                    */
/* ------------------------------------------------------------------ */

#define HUFFMAN_EOF (-1)

typedef struct {
    int value;
    int code_len;
    int code;
} HuffmanEntry;

/* Default Huffman tree — 257 entries (256 byte values + EOF) */
static const HuffmanEntry huffman_tree[] = {
    {0x00, 2, 0x00}, {0x01, 2, 0x01}, {0x02, 3, 0x04}, {0x03, 3, 0x05},
    {0x04, 3, 0x06}, {0x50, 3, 0x07}, {0x05, 4, 0x10}, {0x06, 4, 0x11},
    {0x07, 4, 0x12}, {0x08, 4, 0x13}, {0x09, 4, 0x14}, {0x0a, 4, 0x15},
    {0x0b, 4, 0x16}, {0x0c, 4, 0x17}, {0x0d, 4, 0x18}, {0x0e, 4, 0x19},
    {0x0f, 4, 0x1a}, {0x10, 4, 0x1b}, {0x11, 4, 0x1c}, {0x12, 4, 0x1d},
    {0x13, 4, 0x1e}, {0x14, 4, 0x1f}, {0x15, 5, 0x40}, {0x16, 5, 0x41},
    {0x17, 5, 0x42}, {0x18, 5, 0x43}, {0x19, 5, 0x44}, {0x1a, 5, 0x45},
    {0x1b, 5, 0x46}, {0x1c, 5, 0x47}, {0x1d, 5, 0x48}, {0x1e, 5, 0x49},
    {0x1f, 5, 0x4a}, {0x20, 5, 0x4b}, {0x21, 5, 0x4c}, {0x22, 5, 0x4d},
    {0x23, 5, 0x4e}, {0x24, 5, 0x4f}, {0x25, 5, 0x50}, {0x26, 5, 0x51},
    {0x27, 5, 0x52}, {0x28, 5, 0x53}, {0x29, 5, 0x54}, {0x2a, 5, 0x55},
    {0x2b, 5, 0x56}, {0x2c, 5, 0x57}, {0x2d, 5, 0x58}, {0x2e, 5, 0x59},
    {0x2f, 5, 0x5a}, {0x30, 5, 0x5b}, {0x31, 5, 0x5c}, {0x32, 5, 0x5d},
    {0x33, 5, 0x5e}, {0x34, 5, 0x5f}, {0x35, 6, 0xc0}, {0x36, 6, 0xc1},
    {0x37, 6, 0xc2}, {0x38, 6, 0xc3}, {0x39, 6, 0xc4}, {0x3a, 6, 0xc5},
    {0x3b, 6, 0xc6}, {0x3c, 6, 0xc7}, {0x3d, 6, 0xc8}, {0x3e, 6, 0xc9},
    {0x3f, 6, 0xca}, {0x40, 6, 0xcb}, {0x41, 6, 0xcc}, {0x42, 6, 0xcd},
    {0x43, 6, 0xce}, {0x44, 6, 0xcf}, {0x45, 6, 0xd0}, {0x46, 6, 0xd1},
    {0x47, 6, 0xd2}, {0x48, 6, 0xd3}, {0x49, 6, 0xd4}, {0x4a, 6, 0xd5},
    {0x4b, 6, 0xd6}, {0x4c, 6, 0xd7}, {0x4d, 6, 0xd8}, {0x4e, 6, 0xd9},
    {0x4f, 6, 0xda}, {0x51, 6, 0xdb}, {0x52, 6, 0xdc}, {0x53, 6, 0xdd},
    {0x54, 6, 0xde}, {0x55, 6, 0xdf}, {0x56, 7, 0x1c0}, {0x57, 7, 0x1c1},
    {0x58, 7, 0x1c2}, {0x59, 7, 0x1c3}, {0x5a, 7, 0x1c4}, {0x5b, 7, 0x1c5},
    {0x5c, 7, 0x1c6}, {0x5d, 7, 0x1c7}, {0x5e, 7, 0x1c8}, {0x5f, 7, 0x1c9},
    {0x60, 7, 0x1ca}, {0x61, 7, 0x1cb}, {0x62, 7, 0x1cc}, {0x63, 7, 0x1cd},
    {0x64, 7, 0x1ce}, {0x65, 7, 0x1cf}, {0x66, 7, 0x1d0}, {0x67, 7, 0x1d1},
    {0x68, 7, 0x1d2}, {0x69, 7, 0x1d3}, {0x6a, 7, 0x1d4}, {0x6b, 7, 0x1d5},
    {0x6c, 7, 0x1d6}, {0x6d, 7, 0x1d7}, {0x6e, 7, 0x1d8}, {0x6f, 7, 0x1d9},
    {0x70, 7, 0x1da}, {0x71, 7, 0x1db}, {0x72, 7, 0x1dc}, {0x73, 7, 0x1dd},
    {0x74, 7, 0x1de}, {0x75, 7, 0x1df}, {0x76, 8, 0x3c0}, {0x77, 8, 0x3c1},
    {0x78, 8, 0x3c2}, {0x79, 8, 0x3c3}, {0x7a, 8, 0x3c4}, {0x7b, 8, 0x3c5},
    {0x7c, 8, 0x3c6}, {0x7d, 8, 0x3c7}, {0x7e, 8, 0x3c8}, {0x7f, 8, 0x3c9},
    {0x80, 8, 0x3ca}, {0x81, 8, 0x3cb}, {0x82, 8, 0x3cc}, {0x83, 8, 0x3cd},
    {0x84, 8, 0x3ce}, {0x85, 8, 0x3cf}, {0x86, 8, 0x3d0}, {0x87, 8, 0x3d1},
    {0x88, 8, 0x3d2}, {0x89, 8, 0x3d3}, {0x8a, 8, 0x3d4}, {0x8b, 8, 0x3d5},
    {0x8c, 8, 0x3d6}, {0x8d, 8, 0x3d7}, {0x8e, 8, 0x3d8}, {0x8f, 8, 0x3d9},
    {0x90, 8, 0x3da}, {0x91, 8, 0x3db}, {0x92, 8, 0x3dc}, {0x93, 8, 0x3dd},
    {0x94, 8, 0x3de}, {0x95, 8, 0x3df}, {0x96, 9, 0x7c0}, {0x97, 9, 0x7c1},
    {0x98, 9, 0x7c2}, {0x99, 9, 0x7c3}, {0x9a, 9, 0x7c4}, {0x9b, 9, 0x7c5},
    {0x9c, 9, 0x7c6}, {0x9d, 9, 0x7c7}, {0x9e, 9, 0x7c8}, {0x9f, 9, 0x7c9},
    {0xa0, 9, 0x7ca}, {0xa1, 9, 0x7cb}, {0xa2, 9, 0x7cc}, {0xa3, 9, 0x7cd},
    {0xa4, 9, 0x7ce}, {0xa5, 9, 0x7cf}, {0xa6, 9, 0x7d0}, {0xa7, 9, 0x7d1},
    {0xa8, 9, 0x7d2}, {0xa9, 9, 0x7d3}, {0xaa, 9, 0x7d4}, {0xab, 9, 0x7d5},
    {0xac, 9, 0x7d6}, {0xad, 9, 0x7d7}, {0xae, 9, 0x7d8}, {0xaf, 9, 0x7d9},
    {0xb0, 9, 0x7da}, {0xb1, 9, 0x7db}, {0xb2, 9, 0x7dc}, {0xb3, 9, 0x7dd},
    {0xb4, 9, 0x7de}, {0xb5, 9, 0x7df}, {0xb6, 10, 0xfc0}, {0xb7, 10, 0xfc1},
    {0xb8, 10, 0xfc2}, {0xb9, 10, 0xfc3}, {0xba, 10, 0xfc4}, {0xbb, 10, 0xfc5},
    {0xbc, 10, 0xfc6}, {0xbd, 10, 0xfc7}, {0xbe, 10, 0xfc8}, {0xbf, 10, 0xfc9},
    {0xc0, 10, 0xfca}, {0xc1, 10, 0xfcb}, {0xc2, 10, 0xfcc}, {0xc3, 10, 0xfcd},
    {0xc4, 10, 0xfce}, {0xc5, 10, 0xfcf}, {0xc6, 10, 0xfd0}, {0xc7, 10, 0xfd1},
    {0xc8, 10, 0xfd2}, {0xc9, 10, 0xfd3}, {0xca, 10, 0xfd4}, {0xcb, 10, 0xfd5},
    {0xcc, 10, 0xfd6}, {0xcd, 10, 0xfd7}, {0xce, 10, 0xfd8}, {0xcf, 10, 0xfd9},
    {0xd0, 10, 0xfda}, {0xd1, 10, 0xfdb}, {0xd2, 10, 0xfdc}, {0xd3, 10, 0xfdd},
    {0xd4, 10, 0xfde}, {0xd5, 10, 0xfdf}, {0xd6, 11, 0x1fc0}, {0xd7, 11, 0x1fc1},
    {0xd8, 11, 0x1fc2}, {0xd9, 11, 0x1fc3}, {0xda, 11, 0x1fc4}, {0xdb, 11, 0x1fc5},
    {0xdc, 11, 0x1fc6}, {0xdd, 11, 0x1fc7}, {0xde, 11, 0x1fc8}, {0xdf, 11, 0x1fc9},
    {0xe0, 11, 0x1fca}, {0xe1, 11, 0x1fcb}, {0xe2, 11, 0x1fcc}, {0xe3, 11, 0x1fcd},
    {0xe4, 11, 0x1fce}, {0xe5, 11, 0x1fcf}, {0xe6, 11, 0x1fd0}, {0xe7, 11, 0x1fd1},
    {0xe8, 11, 0x1fd2}, {0xe9, 11, 0x1fd3}, {0xea, 11, 0x1fd4}, {0xeb, 11, 0x1fd5},
    {0xec, 11, 0x1fd6}, {0xed, 11, 0x1fd7}, {0xee, 11, 0x1fd8}, {0xef, 11, 0x1fd9},
    {0xf0, 11, 0x1fda}, {0xf1, 11, 0x1fdb}, {0xf2, 11, 0x1fdc}, {0xf3, 11, 0x1fdd},
    {0xf4, 11, 0x1fde}, {0xf5, 11, 0x1fdf}, {0xf6, 12, 0x3fc0}, {0xf7, 12, 0x3fc1},
    {0xf8, 12, 0x3fc2}, {0xf9, 12, 0x3fc3}, {0xfa, 12, 0x3fc4}, {0xfb, 12, 0x3fc5},
    {0xfc, 12, 0x3fc6}, {0xfd, 12, 0x3fc7}, {0xfe, 12, 0x3fc8}, {0xff, 12, 0x3fc9},
    {HUFFMAN_EOF, 12, 0x0000},
};

#define HUFFMAN_TREE_SIZE (sizeof(huffman_tree) / sizeof(huffman_tree[0]))
#define HUFFMAN_MAX_CODE_LEN 12

/* Precomputed len_index: first entry index for each code length */
static int huffman_len_index[HUFFMAN_MAX_CODE_LEN + 1];

/* Precomputed lookup table: indexed by (code_len - 1) * 4096 + code */
#define HUFFMAN_LOOKUP_SIZE ((HUFFMAN_MAX_CODE_LEN) * 4096)
static int huffman_lookup[HUFFMAN_LOOKUP_SIZE];

static void
init_huffman_tables(void)
{
    /* Initialize len_index */
    for (int i = 0; i <= HUFFMAN_MAX_CODE_LEN; i++)
        huffman_len_index[i] = -1;
    for (int i = 0; i < (int)HUFFMAN_TREE_SIZE; i++) {
        int cl = huffman_tree[i].code_len;
        if (huffman_len_index[cl] == -1)
            huffman_len_index[cl] = i;
    }

    /* Initialize lookup: -2 means "no match" */
    for (int i = 0; i < HUFFMAN_LOOKUP_SIZE; i++)
        huffman_lookup[i] = -2;
    for (int i = 0; i < (int)HUFFMAN_TREE_SIZE; i++) {
        int cl = huffman_tree[i].code_len;
        int c = huffman_tree[i].code;
        int idx = (cl - 1) * 4096 + c;
        if (idx < HUFFMAN_LOOKUP_SIZE)
            huffman_lookup[idx] = huffman_tree[i].value;
    }
}

static PyObject *
msp_huffman_decode(PyObject *self, PyObject *args)
{
    Py_buffer buf;
    int char_count;
    if (!PyArg_ParseTuple(args, "y*i", &buf, &char_count))
        return NULL;

    const unsigned char *in_data = (const unsigned char *)buf.buf;
    Py_ssize_t in_len = buf.len;

    unsigned char *out = (unsigned char *)PyMem_Malloc(char_count > 0 ? char_count : 1);
    if (!out) {
        PyBuffer_Release(&buf);
        return PyErr_NoMemory();
    }

    int out_pos = 0;
    int code = 0;
    int code_len = 0;
    int test_bit = 0x80;
    Py_ssize_t buf_pos = 0;

    while (buf_pos < in_len && out_pos < char_count) {
        code = (code << 1) & 0xFFFF;
        code_len++;
        if (in_data[buf_pos] & test_bit)
            code |= 0x01;
        test_bit >>= 1;
        if (test_bit == 0) {
            test_bit = 0x80;
            buf_pos++;
        }

        if (code_len >= 1 && code_len <= HUFFMAN_MAX_CODE_LEN) {
            int idx = (code_len - 1) * 4096 + code;
            if (idx < HUFFMAN_LOOKUP_SIZE) {
                int value = huffman_lookup[idx];
                if (value == HUFFMAN_EOF) {
                    break;
                } else if (value != -2) {
                    out[out_pos++] = (unsigned char)value;
                    code = 0;
                    code_len = 0;
                }
            }
        }
    }

    PyObject *result = PyBytes_FromStringAndSize((const char *)out, out_pos);
    PyMem_Free(out);
    PyBuffer_Release(&buf);
    return result;
}

/* ------------------------------------------------------------------ */
/* Module definition                                                  */
/* ------------------------------------------------------------------ */

static PyMethodDef methods[] = {
    {"crc8_xor", msp_crc8_xor, METH_VARARGS,
     "CRC8 XOR checksum for MSP v1."},
    {"crc8_dvb_s2", msp_crc8_dvb_s2, METH_VARARGS,
     "CRC8-DVB-S2 checksum for MSP v2."},
    {"decoder_new", msp_decoder_new, METH_NOARGS,
     "Create a new MSP frame decoder state."},
    {"decode", msp_decode, METH_VARARGS,
     "Decode MSP frames from bytes. Returns list of (version, direction, code, payload)."},
    {"huffman_decode", msp_huffman_decode, METH_VARARGS,
     "Huffman-decode compressed blackbox data."},
    {NULL, NULL, 0, NULL},
};

static struct PyModuleDef module = {
    PyModuleDef_HEAD_INIT,
    "_msp_fast",
    "C-accelerated MSP protocol functions.",
    -1,
    methods,
};

PyMODINIT_FUNC
PyInit__msp_fast(void)
{
    init_huffman_tables();
    return PyModule_Create(&module);
}
