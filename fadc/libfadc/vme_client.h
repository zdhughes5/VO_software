/* vme_client.h - header file for the vme_client library
 *
 * This originally consisted of four separate .h files used with the
 * vme_client library. I thought this was confusing so I combined them into
 * one big file. The files occur in this order: consts.h, names.h,
 * handler.h, client.h. Search for "======" to find where each of the old
 * files start.
 *
 * Marty Olevitch, Dec 00
 */

/*--------------------------------------------------------------------------*/
/* Technical Support Inc.                                                   */
/* 11253 John Galt Blvd.                                                    */
/* Omaha, NE 68137                                                          */
/* (402) 331-4977, Fax (402) 331-7710                                       */
/* Bob Sullivan, sulli@techsi.com                                           */
/*--------------------------------------------------------------------------*/

#ifndef _VME_CLIENT_H
#define _VME_CLIENT_H

/* ======================== consts.h */

/*--------------------------------------------------------------------------*/
/* #defines.                                                                */
/*--------------------------------------------------------------------------*/

#define ERROR_SUCCESS       0               /* OK Return code.               */
#define RESERVED_0          0               /* Reserved value.               */
#define ERROR_SERVER        0xE             /* Error contacting server.      */
#define ERROR               0xFF            /* Error return code.            */
                                            /* function call had bad param.  */
#define V_ERROR_MAPPING_SANS_A_THRESHOLD    0xCD
#define OK                  0               /* OK return code.               */
#define STR_LEN             132             /* Max default string length.    */

/*--------------------------------------------------------------------------*/
/* typedefs                                                                 */
/*--------------------------------------------------------------------------*/

#define LOCAL                     /* LOCAL means nothing.    */
typedef unsigned char   BOOL;
typedef unsigned int    UINT32;
typedef unsigned short  UINT16;
typedef unsigned int    DWORD;
typedef unsigned char   UINT8;
typedef unsigned char   HWND;
typedef char            INT8;
typedef unsigned int    STATUS;
typedef void *          PVOID;

#define VME_NAME        "/VMIC/VMEBus"   /* Name for qnx_name_locate()    */

#define BERR_STR        "BERR"           /* VME Bus Error string.        */
#define BERR_STR_LEN       4

#define IRQ_STR         "IRQ"            /* VME IRQ Interrupt string.    */
#define IRQ_STR_LEN        3

#define MBOX_STR        "MBOX"           /* VME Mailbox Interrupt string    */
#define MBOX_STR_LEN       4

#define INT_ENABLE  "sysVmeIntEnable"    
#define INT_ENABLE_LEN         15    

#define INT_DISABLE "sysVmeIntDisable"
#define INT_DISABLE_LEN        16

#define INT_GEN        "sysVmeBusIntGen"
#define INT_GEN_LEN            15

#define MBOX_ENABLE    "sysMailboxEnable"
#define MBOX_ENABLE_LEN        16

#define AUX_MBOX_ENABLE    "sysAuxMailboxEnable"
#define AUX_MBOX_ENABLE_LEN    19

#define ADD_HANDLER    "addIntrHandler"
#define ADD_HANDLER_LEN     14

#define DEL_HANDLER    "delIntrHandler"
#define DEL_HANDLER_LEN     14

#define MAKE_PTR    "makeVmePointer"
#define MAKE_PTR_LEN        14

#define FREE_PTR    "freeVmePointer"
#define FREE_PTR_LEN        14

#define BUS_REQUEST "vmeReadBusRequestLevel"
#define BUS_REQUEST_LEN     22

#define WIN_ADDR     "vmeGetVmeWindowAdr"
#define WIN_ADDR_LEN        18

#define MBOX_ENABLE    "sysMailboxEnable"
#define MBOX_ENABLE_LEN        16

#define AUX_MBOX_ENABLE    "sysAuxMailboxEnable"
#define AUX_MBOX_ENABLE_LEN        19

#define ADD_HANDLER    "addIntrHandler"
#define ADD_HANDLER_LEN        14

#define DEL_HANDLER    "delIntrHandler"
#define DEL_HANDLER_LEN        14

#define MAKE_PTR    "makeVmePointer"
#define MAKE_PTR_LEN        14

#define FREE_PTR    "freeVmePointer"
#define FREE_PTR_LEN        14

#define BUS_REQUEST "vmeReadBusRequestLevel"
#define BUS_REQUEST_LEN        22

#define TIMEOUT_VALUE "vmeReadBusTimeoutValue"
#define TIMEOUT_VALUE_LEN    22

#define ARB_TIMEOUT "vmeReadArbitrationTimeout"
#define ARB_TIMEOUT_LEN    25

#define ARB_MODE "vmeReadArbitrationMode"
#define ARB_MODE_LEN    22

#define BUS_ENABLE "vmeReadBusEnable"
#define BUS_ENABLE_LEN    16

#define BUS_ERR "vmeReadBUSERR"
#define BUS_ERR_LEN    14

#define RELEASE_MODE "vmeReadBusReleaseMode"
#define RELEASE_MODE_LEN    21

#define REQUEST_LEVEL "vmeReadBusRequestLevel"
#define REQUEST_LEVEL_LEN    22

#define SCON "vmeReadSCON"
#define SCON_LEN    11

#define WRITE_ARB_MODE "vmeWriteArbitrationMode"
#define WRITE_ARB_MODE_LEN    23

#define WRITE_BUS_ENABLE "vmeWriteBusEnable"
#define WRITE_BUS_ENABLE_LEN    17

#define WRITE_RELEASE_MODE "vmeWriteBusReleaseMode"
#define WRITE_RELEASE_MODE_LEN    22


/*----------------------------------------------------------------------*/
/* #defines for the possible address methods available in VME.            */
/*----------------------------------------------------------------------*/

#define A16_WIN 0                /* A16 Access method window.    */
#define A24_WIN 1                /* A24 Access method window.    */
#define A32_WIN 2                /* A32 Access method window.    */
#define SLAVE_RAM_WIN 3          /* Slave RAM Window.            */

/*----------------------------------------------------------------------*/
/* #defines for window configuration.                                    */
/*----------------------------------------------------------------------*/

#define AM_SUPERVISOR      0x10
#define AM_USER            0x20
#define AM_PROGRAM         0x01
#define AM_DATA            0x02

#define AM_SD            0x12        /* AM Supervisor/Data       */
#define AM_UD            0x22        /* AM User/Data             */
#define AM_SP            0x11        /* AM Supervisor/Program    */
#define AM_UP            0x21        /* AM User/Program.         */

#define V_A16UD            0x01      /* A16 Nonprivileged.       */
#define V_A16SD            0x02      /* A16 Supervisory.         */
#define V_A24UD            0x04      /* A24 A24 User/Data        */
#define V_A24UP            0x08      /* A24 User/Program.        */
#define V_A24SD            0x10      /* A24 Super/Data.          */
#define V_A24SP            0x20      /* A24 Super/Program.       */    
#define V_A32UD            0x40      /* A32 User/Data            */
#define V_A32UP            0x80      /* A32 User/Program.        */
#define V_A32SD            0x100     /* A32 Super/Data.          */
#define V_A32SP            0x200     /* A32 Super/Program.       */    

#define SNOOP_LEVEL     4                /* Snoop at VMEBus Server level.    */
#define WRITE_LEVEL    10                /* Debug VMEBus Writes level.        */

#define V_LEVEL_BR0        0x00000000    /* VME Bus Request Level 0. */
#define V_LEVEL_BR1        0x00400000    /* VME Bus Request Level 1. */
#define V_LEVEL_BR2        0x00800000    /* VME Bus Request Level 2. */
#define V_LEVEL_BR3        0x00C00000    /* VME Bus Request Level 3. */

#define V_DATA8            0x00000000    /* VME  8 Bits access max.   */
#define V_DATA16           0x00400000    /* VME 16 Bits access max.   */
#define V_DATA32           0x00800000    /* VME 32 Bits access max.   */

/*------------------------------------------------------------------*/
/* #define to go with the ioworks port.                             */
/*------------------------------------------------------------------*/

#define V_BIG_ENDIAN        0x0001    /* Byte order Big Endian.       */
#define V_LITTLE_ENDIAN     0x0002    /* Byte order Little Endian.    */
#define V_THREAD_SAFE       0x0004    /* Unused in QNX.               */
#define V_NO_BUSERR_CHECK   0x0008    /* Don't check for BERR on read */
#define V_SOFT_BYTE_SWAP    0x0010    /* Swap byte order in software  */

/* =========================== names.h */
/*--------------------------------------------------------------------------*/
/* NAME.C - qnx_name_* function wrappers.                                   */
/* $Id: vme_client.h,v 1.1.1.1 2004/11/17 19:33:31 kosack Exp $               */
/*--------------------------------------------------------------------------*/

/*--------------------------------------------------------------------------*/
/* Technical Support Inc.                                                   */
/* 11253 John Galt Blvd.                                                    */
/* Omaha, NE 68137                                                          */
/* (402) 331-4977, Fax (402) 331-7710                                       */
/* Bob Sullivan, sulli@techsi.com                                           */
/*--------------------------------------------------------------------------*/

/*--------------------------------------------------------------------------*/
/* C Library Include Files.                                                 */
/*--------------------------------------------------------------------------*/

#include <sys/proxy.h>

/*--------------------------------------------------------------------------*/
/* Function Prototypes.                                                     */
/*--------------------------------------------------------------------------*/

int attach_name(char *my_name);
void detach_name(int id);
pid_t locate_name(char *my_name);

/* ====================== handler.h */
/*--------------------------------------------------------------------------*/
/* HANDLER.C - User defineable handlers for VME interrupts here.            */
/* $Id: vme_client.h,v 1.1.1.1 2004/11/17 19:33:31 kosack Exp $               */
/*--------------------------------------------------------------------------*/

/*--------------------------------------------------------------------------*/
/* C Library Include Files.                                                 */
/*--------------------------------------------------------------------------*/

#include <stdio.h>
#include <time.h>
#include <sys/types.h>
#include <signal.h>
#include <string.h>
#include <unistd.h>
#include <sys/kernel.h>
#include <sys/proxy.h>

/*--------------------------------------------------------------------------*/
/* Interrupt handler #defines.                                              */
/*--------------------------------------------------------------------------*/

enum send_flags
{
    SEND_PROXY = 1,       /* Used to send a proxy to the user process.    */
    SEND_USR1,            /* Send signal SIGUSR1 to the user process.     */
    SEND_USR2,            /* Send signal SIGUSR2 to the user process.     */
    CALL_FUNC,            /* Call user replaceable function.              */
    REMOVE_HANDLER,       /* Used to remove the handler.                  */
    MAX_SEND_FLAGS        /* Do not get to here!!!                        */
};

/*--------------------------------------------------------------------------*/
/* #defines for the VME Interrupt vectors that come in.                     */
/*--------------------------------------------------------------------------*/

enum aux_flags
{
    FLAG_BERR = 0x100,       /* Vector value for a VME Bus Error     */
    FLAG_MBOX0,              /* Mailbox 0 vector.                    */
    FLAG_MBOX1,              /* Mailbox 1 vector.                    */
    FLAG_MBOX2,              /* Mailbox 2 vector.                    */
    FLAG_MBOX3,              /* Mailbox 3 vector.                    */
    FLAG_VOWN,               /* VOWN Interrupt.                      */
    FLAG_DMA,                /* VME DMA Interrupt.                   */
    FLAG_PCI_BERR,           /* PCI Bus Error Interrupt.             */
    FLAG_IACK,               /* IACK Interrupt.                      */
    FLAG_SW_INT,             /* Software Interrupt Vector.           */
    FLAG_SYSFAIL,            /* SYSFAIL Interrupt Vector.            */
    FLAG_ACFAIL              /* ACFAIL Interrupt Vector.             */
};

#define MAX_AUX_VECTORS  12         /* Max Auxiliary vectors.        */
#define MAX_IRQ_VECTORS  256        /* Max number of IRQ vectors.    */
                                    /* Total number of handlers      */
#define MAX_HANDLERS    (MAX_IRQ_VECTORS + MAX_AUX_VECTORS)

/*--------------------------------------------------------------------------*/
/* Interrupt handler proxy/signal/function call.                            */
/*--------------------------------------------------------------------------*/

typedef struct intr_handler_struct
{
    pid_t    user_pid;      /* PID of the user process.                   */
    UINT8    action_flag;   /* Flag to indicate what action to take on    */
                            /* This interrupt.                            */
} INTR_HANDLER_STRUCT;    

/*--------------------------------------------------------------------------*/
/* Exportable Function Prototypes.                                          */
/*--------------------------------------------------------------------------*/

/* Call the VME Bus Error handler    */

void vme_bus_error_handler(UINT32 pBus, UINT8 address_method);

/* Call the VME Bus Error handler    */

void vme_irq_handler(UINT8 intrBitNum, UINT16 currentVector);

STATUS addIntrHandler(pid_t user_pid, UINT8 action_flag, UINT16 vector);
STATUS delIntrHandler(pid_t user_pid, UINT16 vector);

DWORD vmeInstallInterruptHandler
(
    DWORD    Reserved_0,    /* Must be zero.                        */
    DWORD    IntNum,        /* IRQ [1-7] this Interrupt will occur  */
                            /* Used to enable that IRQ.             */
    DWORD    ID,            /* Interrupt vector ID.                 */
                            /* Interrupt handler function to call.  */
                            /* Unused in QNX version.               */
    DWORD    (*HandlerFunction) (DWORD ID),
    HWND    hWnd            /* Windows 3.1 only.                    */
                            /* Action flags in QNX.                 */
);

/* ========================= client.h */
/* client.h - VMIC QNX VMEBus Test Functions for user API.    */

/*
modification history
--------------------
01a,03may97,res  Initial version

*/
 
/*--------------------------------------------------------------------------*/
/* Technical Support Inc.                                                   */
/* 11253 John Galt Blvd.                                                    */
/* Omaha, NE 68137                                                          */
/* (402) 331-4977, Fax (402) 331-7710                                       */
/* Bob Sullivan, sulli@techsi.com                                           */
/*--------------------------------------------------------------------------*/

/******************************************************************************
*
* vmeInstallInterruptHandler - enable the user handling of the specified
*                               VME Interrupt.
*
* This routine adds a handler to the VME interrupt specified in vector.
*
* DWORD vmeInstallInterruptHandler
*    (
*        DWORD    Reserved_0,        // Reserved. Must be zero.
*        DWORD    IntNum,            // IRQ [1-7] this Interrupt will occur
*                                    // Used to enable that IRQ.
*        DWORD    ID,                // Interrupt vector ID.
*                                    // Interrupt handler function to call.
*                                    // Unused in QNX version.
*        DWORD    (*HandlerFunction) (DWORD ID),
*        HWND    hWnd                // Windows 3.1 only.
*                                    // Action flags in QNX.
*    )
*
* IntNum - VMEBus IRQ to enable.  Use 0 for none.
*
* ID - The current list of supported vectors include:
*
* IRQx Vectors    0x00 - 0xFF
* FLAG_BERR       0x100        Vector value for a VME Bus Error
* FLAG_MBOX0      0x101        Mailbox 0 vector
* FLAG_MBOX1      0x102        Mailbox 1 vector
* FLAG_MBOX2      0x103        Mailbox 2 vector
* FLAG_MBOX3      0x104        Mailbox 3 vector
*
* DWORD    (*HandlerFunction) (DWORD ID) - Unused.
*
* hWnd - The action_flag specifies the SINGLE action to be taken for this 
* interrupt.  The supported actions include:
*
* SEND_PROXY       0x01        Used to send a proxy to the user process.
* SEND_USR1        0x02        Send signal SIGUSR1 to the user process.
* SEND_USR2        0x03        Send signal SIGUSR2 to the user process.
*
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: int delIntrHandler(pid_t user_pid, UINT16 vector);
*/

DWORD vmeInstallInterruptHandler
(
    DWORD    Reserved_0,    /* Must be cero.                        */
    DWORD    IntNum,        /* IRQ [1-7] this Interrupt will occur  */
                            /* Used to enable that IRQ.             */
    DWORD    ID,            /* Interrupt vector ID.                 */
                            /* Interrupt handler function to call.  */
                            /* Unused in QNX version.               */
    DWORD    (*HandlerFunction) (DWORD ID),
    HWND    hWnd            /* Windows 3.1 only.                    */
                            /* Action flags in QNX.                 */
);

/******************************************************************************
*
* vmeGetSlaveRam - Get a pointer to the VME Slave RAM block.
*
* Get a pointer to the VME Slave RAM block.
* 
* DWORD vmeGetSlaveRam
* (
*     DWORD Reserved;     // Must be 0.
*     DWORD *VmeAdr;      // Pointer to Desired VME Address.
*                         // Returns actual VME Address.
*     DWORD *Blocksize;   // Number of bytes/actual bytes to share
*     void **SlaveBase;   // Pointer to the block.
*     DWORD *AccessMode;  // Access mode. One of:
*                         // V_A16UD - Nonprivileged.
*                         // V_A16SD - Supervisory.
*                         // V_A24UD - A24 User/Data
*                         // V_A24UP - A24 User/Program.
*                         // V_A24SD - A24 Super/Data.
*                         // V_A24SP - A24 Super/Program.
*                         // V_A32UD - A32 User/Data
*                         // V_A32UP - A32 User/Program.
*                         // V_A32SD - A32 Super/Data.
*                         // V_A32SP - A32 Super/Program.
*     DWORD *Endian;      // Byte Swapping order. One of:
*                         // V_BIG_ENDIAN
*                         // V_LITTLE_ENDIAN
*     DWORD Reserved2;    // Must be 0.
* );
*
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: 
*/

DWORD vmeGetSlaveRam
(
    DWORD Reserved,     /* Must be 0.                           */
    DWORD *VmeAdr,      /* Pointer to Desired VME Address.      */
                        /* Returns actual VME Address.          */
    DWORD *Blocksize,   /* Number of bytes/actual bytes to share*/
    void **SlaveBase,   /* Pointer to the block.         */
    DWORD *AccessMode,  /* Access mode. One of:          */
                        /* V_A16UD - Nonprivileged.      */
                        /* V_A16SD - Supervisory.        */
                        /* V_A24UD - A24 User/Data       */
                        /* V_A24UP - A24 User/Program.   */
                        /* V_A24SD - A24 Super/Data.     */
                        /* V_A24SP - A24 Super/Program.  */    
                        /* V_A32UD - A32 User/Data       */
                        /* V_A32UP - A32 User/Program.   */
                        /* V_A32SD - A32 Super/Data.     */
                        /* V_A32SP - A32 Super/Program.  */    
    DWORD *Endian,      /* Byte Swapping order. One of:  */
                        /* V_BIG_ENDIAN                  */
                        /* V_LITTLE_ENDIAN               */
    DWORD Reserved2     /* Must be 0.                    */
);

/******************************************************************************
*
* vmeReleasePointer - Release pointer to the VME Slave RAM block.
*
* This routine releases pointer resources to the VME Slave RAM block.
*
* DWORD vmeReleasePointer
*     (
*         DWORD    Reserved_0,
*         PVOID    Pointer,     // SlaveBase pointer returned by the
*                               // vmeGetSlaveRam function call.
*         DWORD    PCI_addr,    // PCI_addr from vmeGetSlaveRam call.
*         DWORD    size         // size of the pointer.
*     )
* 
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: 
*/

DWORD vmeReleasePointer
    (
        DWORD    Reserved_0,
        PVOID    Pointer,    /* SlaveBase pointer returned by the    */
                             /* vmeGetSlaveRam function call.        */
        DWORD    size        /* size of the pointer.                 */
    );

/******************************************************************************
*
* vmeGenerateInterrupt - generate/remove a VME bus interrupt
*
* This routine generates an VME bus interrupt for a specified IntNum (1-7) 
* with a specified ID (0x00 - 0xFF).
*
* NOTES: The Universe device ignores the least significant bit of the value programmed
* into the vector register.  The least significant bit of the vector is a 1 if the
* interrupt is a result of a hardware condition (i.e. VME bus error, DMA complete, etc.),
* or is a 0 if the interrupt is a software interrupt as in this case. 
*
* RETURNS: ERROR_SUCCESS on success, or one of the following error codes:
*          V_ERROR_MAPPING_SANS_A_THRESHOLD - function call had bad parameter.
*          ERROR_SERVER - Error locating VMEBus server.
*/

DWORD vmeGenerateInterrupt (
        DWORD Reserved_0,   /* Must be 0.                               */
        DWORD IntNum,       /* IRQ [1-7]                                */
        DWORD ID,           /* Vector 0x00 - 0xFF                       */
        DWORD Enable );     /* 1 - Enable Interrupt,                    */
                            /* 0 - Remove this Interrupt.               */

/******************************************************************************
*
* vmeLockVmeWindow
*
* This routine accesses a VME window for later use. 
*
* DWORD vmeLockVmeWindow
*     (
*         DWORD    Reserved_0,    // Must be 0.
*         DWORD    Size,          // V_DATA8, V_DATA16, V_DATA32
*         DWORD    Adr,           // VMEBus Address to map.
*         DWORD     *Handle,      // Locked window identifier.
*         DWORD    NumElements,   // Number of elements to map.
*         DWORD    AccessMode,    // Access mode - V_A16UD, etc.
*         DWORD    Flags,         // OR of the following flags:
*                                 // V_BIG_ENDIAN
*                                 // V_LITTLE_ENDIAN
*                                 // V_THREAD_UNSAFE
*                                 // V_NO_BUSERR_CHECK - skip BERR check.
*                                 // V_SOFT_BYTE_SWAP
*         DWORD    RequestLevel,  // VMEBus Requext level.  One of:
*                                 // V_LEVEL_BR0
*                                 // V_LEVEL_BR1
*                                 // V_LEVEL_BR2
*                                 // V_LEVEL_BR3
*         DWORD    Timeout;       // VMEBus Timeout value.
*         DWORD    Reserved_1;    // Must be 0.
*     )
* 
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: 
*/

DWORD vmeLockVmeWindow
    (
        DWORD    Reserved_0,    /* Must be 0.                       */
        DWORD    Size,          /* V_DATA8, V_DATA16, V_DATA32      */
        DWORD    Adr,           /* VMEBus Address to map.           */
        DWORD    *Handle,       /* Locked window identifier.        */
        DWORD    NumElements,   /* Number of elements to map.       */
        DWORD    AccessMode,    /* Access mode - V_A16UD, etc.      */
        DWORD    Flags,         /* OR of the following flags:       */
                                /* V_BIG_ENDIAN                     */
                                /* V_LITTLE_ENDIAN                  */
                                /* V_THREAD_UNSAFE                  */
                                /* V_NO_BUSERR_CHECK - skip BERR check.    */
                                /* V_SOFT_BYTE_SWAP                 */
        DWORD    RequestLevel,  /* VMEBus Requext level.  One of:   */
                                /* V_LEVEL_BR0                      */
                                /* V_LEVEL_BR1                      */
                                /* V_LEVEL_BR2                      */
                                /* V_LEVEL_BR3                      */
        DWORD    Timeout,       /* VMEBus Timeout value.            */
        DWORD    Reserved_1     /* Must be 0.                       */
    );

/******************************************************************************
*
* vmeGetVmeWindowAdr
*
* This routine creates a pointer to a VME Window.    
* vmeLockVmeWindow must have already been called to get the handle to the
* window.
*
* DWORD vmeGetVmeWindowAdr
*    (
*        DWORD Reserved_0,       // Must be 0.
*        DWORD WinHandle,        // Handle from a call to vmeLockVmeWindow
*        void  **adr             // Address of the window.
*    )
*
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: 
*/

DWORD vmeGetVmeWindowAdr
(
    DWORD Reserved_0,   /* Must be 0.                             */
    DWORD WinHandle,    /* Handle from a call to vmeLockVmeWindow */
    void  **adr         /* Address of the window.                 */
);

/******************************************************************************
*
* vmeFreeVmeWindowAdr
*
* This routine frees a pointer to a VME Window.    
* vmeGetVmeWindowAdr must have already been called to get the pointer to the
* window.
*
* DWORD vmeFreeVmeWindowAdr
*     (
*         DWORD    Reserved_0,    // Must be 0.
*         DWORD    WinHandle,     // handle to remove.
*         void    *Adr            // Pointer address from
*                                 // vmeGetVmeWindowAdr.
*     )
*
* RETURNS: ERROR_SUCCESS or ERROR
*
* SEE ALSO: 
*/

DWORD vmeFreeVmeWindowAdr
    (
        DWORD    Reserved_0,    /* Must be 0.           */
        DWORD    WinHandle,     /* handle to remove.    */
        void    *Adr            /* Pointer address from */
                                /* vmeGetVmeWindowAdr.  */    
    );

#endif /* _VME_CLIENT_H */
