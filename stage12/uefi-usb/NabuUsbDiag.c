/** @file
  Non-destructive nabu UEFI host-side USB diagnostics.
  Enumerates existing UEFI protocols. No firmware variables or disk writes.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Protocol/Usb2HostController.h>
#include <Protocol/UsbIo.h>
#include <Protocol/SimpleTextIn.h>
#include <Protocol/SimpleTextInEx.h>
#include <Protocol/SimpleFileSystem.h>

STATIC
UINTN
CountProtocol (
  IN CONST CHAR16  *Name,
  IN EFI_GUID      *Guid,
  OUT EFI_HANDLE   **HandleList
  )
{
  EFI_STATUS  Status;
  UINTN       Count;

  Count       = 0;
  *HandleList = NULL;
  Status      = gBS->LocateHandleBuffer (ByProtocol, Guid, NULL, &Count, HandleList);

  Print (L"%-19s %u  (%r)\r\n", Name, (UINT32)Count, Status);
  return EFI_ERROR (Status) ? 0 : Count;
}

STATIC
VOID
ReadUsbHostInfo (VOID)
{
  EFI_HANDLE            *Handles;
  EFI_USB2_HC_PROTOCOL  *Hc;
  EFI_USB_PORT_STATUS   PortStatus;
  EFI_STATUS            Status;
  UINTN                 Count;
  UINTN                 Index;
  UINT8                 MaxSpeed;
  UINT8                 Ports;
  UINT8                 Is64;
  UINT8                 Port;

  Count = CountProtocol (L"EFI_USB2_HC", &gEfiUsb2HcProtocolGuid, &Handles);
  for (Index = 0; Index < Count && Index < 4; Index++) {
    Hc = NULL;
    Status = gBS->HandleProtocol (Handles[Index], &gEfiUsb2HcProtocolGuid, (VOID **)&Hc);
    if (EFI_ERROR (Status) || Hc == NULL) {
      Print (L"  HC[%u] open: %r\r\n", (UINT32)Index, Status);
      continue;
    }

    MaxSpeed = 0;
    Ports    = 0;
    Is64     = 0;
    Status = Hc->GetCapability (Hc, &MaxSpeed, &Ports, &Is64);
    Print (L"  HC[%u] ports=%u speed=%u cap=%r\r\n",
           (UINT32)Index, (UINT32)Ports, (UINT32)MaxSpeed, Status);

    if (!EFI_ERROR (Status)) {
      for (Port = 0; Port < Ports && Port < 4; Port++) {
        PortStatus.PortStatus = 0;
        PortStatus.PortChangeStatus = 0;
        Status = Hc->GetRootHubPortStatus (Hc, Port, &PortStatus);
        if (!EFI_ERROR (Status)) {
          Print (L"    port%u raw=%04x power=%u conn=%u\r\n",
                 (UINT32)Port, (UINT32)PortStatus.PortStatus,
                 (UINT32)((PortStatus.PortStatus & USB_PORT_STAT_POWER) != 0),
                 (UINT32)((PortStatus.PortStatus & USB_PORT_STAT_CONNECTION) != 0));
        } else {
          Print (L"    port%u status=%r\r\n", (UINT32)Port, Status);
        }
      }
    }
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }
}

STATIC
VOID
ReadUsbDevices (VOID)
{
  EFI_HANDLE                *Handles;
  EFI_USB_IO_PROTOCOL       *UsbIo;
  EFI_USB_DEVICE_DESCRIPTOR  Dev;
  EFI_USB_INTERFACE_DESCRIPTOR  Iface;
  EFI_STATUS                DevStatus;
  EFI_STATUS                IfaceStatus;
  EFI_STATUS                Status;
  UINTN                     Count;
  UINTN                     Index;

  Count = CountProtocol (L"EFI_USB_IO", &gEfiUsbIoProtocolGuid, &Handles);
  for (Index = 0; Index < Count && Index < 8; Index++) {
    UsbIo = NULL;
    Status = gBS->HandleProtocol (Handles[Index], &gEfiUsbIoProtocolGuid, (VOID **)&UsbIo);
    if (EFI_ERROR (Status) || UsbIo == NULL) {
      Print (L"  USB[%u] open: %r\r\n", (UINT32)Index, Status);
      continue;
    }

    DevStatus   = UsbIo->UsbGetDeviceDescriptor (UsbIo, &Dev);
    IfaceStatus = UsbIo->UsbGetInterfaceDescriptor (UsbIo, &Iface);

    if (EFI_ERROR (DevStatus) || EFI_ERROR (IfaceStatus)) {
      Print (L"  USB[%u] desc=%r iface=%r\r\n",
             (UINT32)Index, DevStatus, IfaceStatus);
    } else {
      Print (L"  USB[%u] %04x:%04x if=%02x/%02x/%02x\r\n",
             (UINT32)Index, Dev.IdVendor, Dev.IdProduct,
             Iface.InterfaceClass, Iface.InterfaceSubClass, Iface.InterfaceProtocol);
    }
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }
}

EFI_STATUS
EFIAPI
UefiMain (
  IN EFI_HANDLE         ImageHandle,
  IN EFI_SYSTEM_TABLE   *SystemTable
  )
{
  EFI_HANDLE  *Handles;

  (VOID)ImageHandle;
  (VOID)SystemTable;

  Print (L"\r\n=== NABU USB DIAG 01 (READ ONLY) ===\r\n");
  Print (L"UEFI driver presence != host/keyboard functionality\r\n");

  ReadUsbHostInfo ();
  ReadUsbDevices ();

  CountProtocol (L"EFI_TEXT_INPUT", &gEfiSimpleTextInProtocolGuid, &Handles);
  if (Handles != NULL) {
    FreePool (Handles);
  }
  CountProtocol (L"EFI_TEXT_INPUT_EX", &gEfiSimpleTextInputExProtocolGuid, &Handles);
  if (Handles != NULL) {
    FreePool (Handles);
  }
  CountProtocol (L"EFI_SIMPLE_FS", &gEfiSimpleFileSystemProtocolGuid, &Handles);
  if (Handles != NULL) {
    FreePool (Handles);
  }

  Print (L"=== END - photograph this screen ===\r\n");
  Print (L"No device partitions or NVRAM were modified.\r\n\r\n");
  return EFI_SUCCESS;
}
