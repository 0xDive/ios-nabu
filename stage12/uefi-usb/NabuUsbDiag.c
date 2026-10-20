/** @file
  Read-only nabu USB firmware diagnostics.
  No ConnectController(), writes, NVRAM access, or PCI register access.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Protocol/DevicePath.h>
#include <Protocol/Usb2HostController.h>
#include <Protocol/UsbHostController.h>
#include <Protocol/UsbFunctionIo.h>
#include <Protocol/UsbIo.h>
#include <Protocol/PciIo.h>
#include <Protocol/PciRootBridgeIo.h>
#include <Protocol/PciHostBridgeResourceAllocation.h>
#include <Pi/PiFirmwareFile.h>
#include <Pi/PiFirmwareVolume.h>
#include <Pi/PiDependency.h>
#include <Protocol/FirmwareVolume2.h>
#include <Protocol/Metronome.h>
#include <Protocol/PiPcd.h>
#include <Protocol/DriverBinding.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleTextIn.h>
#include <Protocol/SimpleTextInEx.h>

typedef struct {
  CONST CHAR16  *Name;
  EFI_GUID      FileGuid;
  BOOLEAN       Loaded;
  BOOLEAN       Binding;
} DRIVER_RECORD;

// Exact firmware-file GUIDs from pinned edk2-msm SM8150 FDF.
STATIC DRIVER_RECORD  mDrivers[] = {
  { L"UsbPwrCtrl",  {0x11faed4c, 0xb21f, 0x4d88, {0x8e,0x48,0xc4,0xc2,0x8a,0x1e,0x50,0xdf}}, FALSE, FALSE },
  { L"UsbInit",     {0x0a134f0e, 0x075e, 0x40b3, {0x9c,0x63,0x3b,0x39,0x06,0x80,0x46,0x63}}, FALSE, FALSE },
  { L"UsbConfig",   {0xcd823a4d, 0x7dec, 0x4531, {0xae,0x5d,0x41,0x34,0xfa,0x41,0x27,0xb8}}, FALSE, FALSE },
  { L"XhciPciEmu",  {0xbeb12bee, 0xf6e1, 0x11e1, {0x9f,0xb8,0x6c,0x62,0x6d,0xe4,0xae,0xb1}}, FALSE, FALSE },
  { L"XhciDxe",     {0xb7f50e91, 0xa759, 0x412c, {0xad,0xe4,0xdc,0xd0,0x3e,0x7f,0x7c,0x28}}, FALSE, FALSE },
  { L"UsbBusDxe",   {0x240612b7, 0xa063, 0x11d4, {0x9a,0x3a,0x00,0x90,0x27,0x3f,0xc1,0x4d}}, FALSE, FALSE },
  { L"UsbKbDxe",    {0x2d2e62cf, 0x9ecf, 0x43b7, {0x82,0x19,0x94,0xe7,0xfc,0x71,0x3d,0xfe}}, FALSE, FALSE },
  { L"PciHostBridge",{0xc62f4b20,0x681e, 0x11df, {0x8f,0x0d,0x00,0x02,0xa5,0xd5,0xc5,0x1b}}, FALSE, FALSE },
  { L"UsbFnDwc3",   {0x94f8a6a7,0xdc34, 0x4101, {0x88,0xc1,0x99,0x17,0x9c,0xce,0xae,0x83}}, FALSE, FALSE }
};

STATIC
UINTN
ProtocolCount (
  IN CONST CHAR16  *Name,
  IN EFI_GUID      *Guid
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  *Handles;
  UINTN       Count;

  Handles = NULL;
  Count   = 0;
  Status = gBS->LocateHandleBuffer (ByProtocol, Guid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    Count = 0;
  }

  Print (L" %-19s %u\r\n", Name, (UINT32)Count);

  if (Handles != NULL) {
    FreePool (Handles);
  }

  return Count;
}

STATIC
VOID
RecordImage (
  IN EFI_LOADED_IMAGE_PROTOCOL  *Image,
  IN BOOLEAN                    DriverBindingPresent
  )
{
  EFI_DEVICE_PATH_PROTOCOL            *Path;
  MEDIA_FW_VOL_FILEPATH_DEVICE_PATH   *FvPath;
  UINTN                               Node;
  UINTN                               Index;
  UINTN                               Length;

  if ((Image == NULL) || (Image->FilePath == NULL)) {
    return;
  }

  Path = Image->FilePath;
  for (Node = 0; Node < 16 && !IsDevicePathEnd (Path); Node++) {
    Length = DevicePathNodeLength (Path);
    if ((Length < sizeof (EFI_DEVICE_PATH_PROTOCOL)) || (Length > 256)) {
      break;
    }

    if ((DevicePathType (Path) == MEDIA_DEVICE_PATH) &&
        (DevicePathSubType (Path) == MEDIA_PIWG_FW_FILE_DP) &&
        (Length >= sizeof (MEDIA_FW_VOL_FILEPATH_DEVICE_PATH))) {
      FvPath = (MEDIA_FW_VOL_FILEPATH_DEVICE_PATH *)Path;
      for (Index = 0; Index < sizeof (mDrivers)/sizeof (mDrivers[0]); Index++) {
        if (CompareGuid (&FvPath->FvFileName, &mDrivers[Index].FileGuid)) {
          mDrivers[Index].Loaded = TRUE;
          if (DriverBindingPresent) {
            mDrivers[Index].Binding = TRUE;
          }
        }
      }
    }

    Path = NextDevicePathNode (Path);
  }
}

STATIC
VOID
ReportLoadedDrivers (VOID)
{
  EFI_STATUS                   Status;
  EFI_HANDLE                   *Handles;
  EFI_LOADED_IMAGE_PROTOCOL    *Image;
  EFI_DRIVER_BINDING_PROTOCOL  *Binding;
  UINTN                        Count;
  UINTN                        Index;

  Print (L"\r\n Driver         image / binding\r\n");
  Print (L" (FV image match; not proof of Started())\r\n");

  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (
                  ByProtocol, &gEfiLoadedImageProtocolGuid,
                  NULL, &Count, &Handles);
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count; Index++) {
      Image = NULL;
      Status = gBS->HandleProtocol (
                      Handles[Index], &gEfiLoadedImageProtocolGuid,
                      (VOID **)&Image);
      if (!EFI_ERROR (Status)) {
        RecordImage (Image, FALSE);
      }
    }
  }
  if (Handles != NULL) {
    FreePool (Handles);
  }

  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (
                  ByProtocol, &gEfiDriverBindingProtocolGuid,
                  NULL, &Count, &Handles);
  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count; Index++) {
      Binding = NULL;
      Status = gBS->HandleProtocol (
                      Handles[Index], &gEfiDriverBindingProtocolGuid,
                      (VOID **)&Binding);
      if (EFI_ERROR (Status) || Binding == NULL) {
        continue;
      }

      Image = NULL;
      Status = gBS->HandleProtocol (
                      Binding->ImageHandle, &gEfiLoadedImageProtocolGuid,
                      (VOID **)&Image);
      if (!EFI_ERROR (Status)) {
        RecordImage (Image, TRUE);
      }
    }
  }
  if (Handles != NULL) {
    FreePool (Handles);
  }

  for (Index = 0; Index < sizeof (mDrivers)/sizeof (mDrivers[0]); Index++) {
    Print (L" %-15s %s / %s\r\n",
           mDrivers[Index].Name,
           mDrivers[Index].Loaded ? L"Y" : L"-",
           mDrivers[Index].Binding ? L"Y" : L"-");
  }
}

STATIC
VOID
ReportPciFirmwareFile (VOID)
{
  EFI_STATUS                      Status;
  EFI_STATUS                      OpenStatus;
  EFI_HANDLE                      *Handles;
  EFI_FIRMWARE_VOLUME2_PROTOCOL   *Fv;
  EFI_FV_FILETYPE                 FileType;
  EFI_FV_FILE_ATTRIBUTES          FileAttributes;
  VOID                            *Data;
  UINTN                           FileSize;
  UINT32                          Authentication;
  UINTN                           Count;
  UINTN                           Index;

  Print (L"\r\n PciHostBridge image in firmware volume:\r\n");
  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (
                  ByProtocol,
                  &gEfiFirmwareVolume2ProtocolGuid,
                  NULL,
                  &Count,
                  &Handles);
  if (EFI_ERROR (Status)) {
    Print (L" FV2 unavailable: %r\r\n", Status);
    return;
  }

  for (Index = 0; Index < Count && Index < 4; Index++) {
    Fv = NULL;
    OpenStatus = gBS->HandleProtocol (
                        Handles[Index],
                        &gEfiFirmwareVolume2ProtocolGuid,
                        (VOID **)&Fv);
    if (EFI_ERROR (OpenStatus) || Fv == NULL) {
      Print (L"  FV[%u] open: %r\r\n", (UINT32)Index, OpenStatus);
      continue;
    }

    Data = NULL;
    FileSize = 0;
    FileType = (EFI_FV_FILETYPE)0;
    FileAttributes = 0;
    Authentication = 0;
    Status = Fv->ReadFile (
                   Fv,
                   &mDrivers[7].FileGuid,
                   &Data,
                   &FileSize,
                   &FileType,
                   &FileAttributes,
                   &Authentication);
    Print (L"  FV[%u] PCI file: %r size=%u\r\n",
           (UINT32)Index, Status, (UINT32)FileSize);

    if (Data != NULL) {
      FreePool (Data);
    }
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }
}

//
// Inspect DEPEX from installed FV files without dispatching any drivers.
//
// EFI DEP expression is postfix (PUSH GUID, AND, OR, NOT, TRUE/FALSE, END).
// These checks are snapshots of installed UEFI protocols at Shell entry.
//
STATIC
VOID
CheckDepex (
  IN CONST CHAR16  *DriverName,
  IN EFI_GUID      *FileGuid
  )
{
  EFI_STATUS                     Status;
  EFI_HANDLE                     *Handles;
  EFI_FIRMWARE_VOLUME2_PROTOCOL  *Fv;
  UINTN                          Count;
  UINTN                          Index;
  VOID                           *Buffer;
  UINTN                          BufferSize;
  UINT32                         AuthStatus;
  BOOLEAN                        Stack[32];
  UINTN                          Sp;
  UINTN                          Offset;
  BOOLEAN                        Valid;
  BOOLEAN                        Complete;
  BOOLEAN                        Value;
  BOOLEAN                        Special;
  EFI_GUID                       ProtocolGuid;
  VOID                           *Interface;
  UINTN                          MissingPushCount;
  UINT32                         FirstMissing;

  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (
                  ByProtocol,
                  &gEfiFirmwareVolume2ProtocolGuid,
                  NULL,
                  &Count,
                  &Handles);
  if (EFI_ERROR (Status)) {
    Print (L" %-14s FV2 absent: %r\r\n", DriverName, Status);
    return;
  }

  Buffer = NULL;
  BufferSize = 0;
  Status = EFI_NOT_FOUND;

  for (Index = 0; Index < Count && Index < 4; Index++) {
    Fv = NULL;
    if (EFI_ERROR (gBS->HandleProtocol (
                          Handles[Index],
                          &gEfiFirmwareVolume2ProtocolGuid,
                          (VOID **)&Fv)) || Fv == NULL) {
      continue;
    }

    Buffer = NULL;
    BufferSize = 0;
    AuthStatus = 0;
    Status = Fv->ReadSection (
                   Fv,
                   FileGuid,
                   EFI_SECTION_DXE_DEPEX,
                   0,
                   &Buffer,
                   &BufferSize,
                   &AuthStatus);
    if (!EFI_ERROR (Status)) {
      break;
    }

    if (Buffer != NULL) {
      FreePool (Buffer);
      Buffer = NULL;
    }

    if (Status != EFI_NOT_FOUND) {
      break;
    }
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }

  if (EFI_ERROR (Status)) {
    Print (L" %-14s DXE_DEPEX %r\r\n", DriverName, Status);
    return;
  }

  if ((Buffer == NULL) || (BufferSize == 0) || (BufferSize > 512)) {
    Print (L" %-14s invalid DEP len=%u\r\n", DriverName, (UINT32)BufferSize);
    if (Buffer != NULL) {
      FreePool (Buffer);
    }
    return;
  }

  Sp = 0;
  Offset = 0;
  Valid = TRUE;
  Complete = FALSE;
  Special = FALSE;
  Value = FALSE;
  MissingPushCount = 0;
  FirstMissing = 0;

  while ((Offset < BufferSize) && Valid && !Complete) {
    UINT8 Op;

    Op = ((UINT8 *)Buffer)[Offset++];
    switch (Op) {
      case EFI_DEP_PUSH:
        if (((BufferSize - Offset) < sizeof (EFI_GUID)) ||
            (Sp >= sizeof (Stack)/sizeof (Stack[0]))) {
          Valid = FALSE;
          break;
        }

        CopyMem (&ProtocolGuid, ((UINT8 *)Buffer) + Offset, sizeof (EFI_GUID));
        Offset += sizeof (EFI_GUID);
        Interface = NULL;
        Value = !EFI_ERROR (
                   gBS->LocateProtocol (&ProtocolGuid, NULL, &Interface));

        if (!Value) {
          MissingPushCount++;
          if (FirstMissing == 0) {
            FirstMissing = ProtocolGuid.Data1;
          }
        }

        Stack[Sp++] = Value;
        break;

      case EFI_DEP_TRUE:
      case EFI_DEP_FALSE:
        if (Sp >= sizeof (Stack)/sizeof (Stack[0])) {
          Valid = FALSE;
        } else {
          Stack[Sp++] = (Op == EFI_DEP_TRUE);
        }
        break;

      case EFI_DEP_NOT:
        if (Sp < 1) {
          Valid = FALSE;
        } else {
          Stack[Sp-1] = !Stack[Sp-1];
        }
        break;

      case EFI_DEP_AND:
      case EFI_DEP_OR:
        if (Sp < 2) {
          Valid = FALSE;
        } else {
          BOOLEAN Right;
          Right = Stack[--Sp];
          Stack[Sp-1] = (Op == EFI_DEP_AND)
                          ? (Stack[Sp-1] && Right)
                          : (Stack[Sp-1] || Right);
        }
        break;

      case EFI_DEP_SOR:
        // Schedule-on-request additionally depends on DXE dispatch policy.
        Special = TRUE;
        break;

      case EFI_DEP_BEFORE:
      case EFI_DEP_AFTER:
        // Ordering expressions cannot be truth-evaluated like PUSH/AND/OR.
        Special = TRUE;
        Complete = TRUE;
        break;

      case EFI_DEP_END:
        Complete = TRUE;
        break;

      default:
        Valid = FALSE;
        break;
    }
  }

  if (!Valid || !Complete || (Sp != 1) || (Offset != BufferSize)) {
    if (!Special) {
      Print (L" %-14s DEP malformed (%u B)\r\n",
             DriverName, (UINT32)BufferSize);
    } else {
      Print (L" %-14s ordering/SOR DEP (%u B)\r\n",
             DriverName, (UINT32)BufferSize);
    }
  } else {
    Print (L" %-14s dep=%s pushmiss=%u\r\n",
           DriverName,
           Special ? L"SOR" : (Stack[0] ? L"TRUE" : L"FALSE"),
           (UINT32)MissingPushCount);
    if (MissingPushCount != 0) {
      Print (L"   first missing GUID.Data1=%08x\r\n", FirstMissing);
    }
  }

  FreePool (Buffer);
}

STATIC
VOID
ReportDepex (VOID)
{
  Print (L"\r\n DXE dispatch dependencies in FV:\r\n");
  CheckDepex (L"PciHostBridge", &mDrivers[7].FileGuid);
  CheckDepex (L"XhciPciEmu", &mDrivers[3].FileGuid);
  CheckDepex (L"UsbInit", &mDrivers[1].FileGuid);
  CheckDepex (L"UsbConfig", &mDrivers[2].FileGuid);
  CheckDepex (L"UsbPwrCtrl", &mDrivers[0].FileGuid);
}

STATIC
VOID
ReportHostPort (VOID)
{
  EFI_STATUS            Status;
  EFI_HANDLE            *Handles;
  EFI_USB2_HC_PROTOCOL  *Hc;
  EFI_USB_PORT_STATUS   PortStatus;
  UINTN                 Count;
  UINTN                 Index;
  UINT8                 MaxSpeed;
  UINT8                 Ports;
  UINT8                 Is64;
  UINT8                 Port;

  Handles = NULL;
  Count = 0;
  Status = gBS->LocateHandleBuffer (
                  ByProtocol, &gEfiUsb2HcProtocolGuid,
                  NULL, &Count, &Handles);

  if (!EFI_ERROR (Status)) {
    for (Index = 0; Index < Count && Index < 2; Index++) {
      Hc = NULL;
      Status = gBS->HandleProtocol (
                      Handles[Index], &gEfiUsb2HcProtocolGuid, (VOID **)&Hc);
      if (EFI_ERROR (Status) || Hc == NULL) {
        continue;
      }

      MaxSpeed = 0;
      Ports = 0;
      Is64 = 0;
      Status = Hc->GetCapability (Hc, &MaxSpeed, &Ports, &Is64);
      Print (L" HC[%u] cap=%r ports=%u\r\n",
             (UINT32)Index, Status, (UINT32)Ports);

      if (!EFI_ERROR (Status)) {
        for (Port = 0; Port < Ports && Port < 2; Port++) {
          PortStatus.PortStatus = 0;
          PortStatus.PortChangeStatus = 0;
          Status = Hc->GetRootHubPortStatus (Hc, Port, &PortStatus);
          Print (L"  port%u %r stat=0x%04x\r\n",
                 (UINT32)Port, Status, (UINT32)PortStatus.PortStatus);
        }
      }
    }
  }

  if (Handles != NULL) {
    FreePool (Handles);
  }
}

EFI_STATUS
EFIAPI
UefiMain (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  (VOID)ImageHandle;
  (VOID)SystemTable;

  Print (L"\r\n=== NABU USB DIAG 04: READ ONLY ===\r\n");
  Print (L"PCI bridge .depex = METRONOME AND PCD\r\n");
  ProtocolCount (L"METRONOME (REQUIRED)", &gEfiMetronomeArchProtocolGuid);
  ProtocolCount (L"PCD (REQUIRED)", &gEfiPcdProtocolGuid);
  ProtocolCount (L"PCI_HOST_RESOURCE", &gEfiPciHostBridgeResourceAllocationProtocolGuid);
  ProtocolCount (L"FIRMWARE_VOLUME2", &gEfiFirmwareVolume2ProtocolGuid);
  ProtocolCount (L"PCI_ROOT_BRIDGE_IO", &gEfiPciRootBridgeIoProtocolGuid);
  ProtocolCount (L"PCI_IO", &gEfiPciIoProtocolGuid);
  ProtocolCount (L"USB2_HC", &gEfiUsb2HcProtocolGuid);
  ProtocolCount (L"USB_HC_LEGACY", &gEfiUsbHcProtocolGuid);
  ProtocolCount (L"USB_IO", &gEfiUsbIoProtocolGuid);
  ProtocolCount (L"USBFN_DEVICE", &gEfiUsbFunctionIoProtocolGuid);
  ProtocolCount (L"DRIVER_BINDING", &gEfiDriverBindingProtocolGuid);
  ProtocolCount (L"TEXT_INPUT", &gEfiSimpleTextInProtocolGuid);
  ProtocolCount (L"TEXT_INPUT_EX", &gEfiSimpleTextInputExProtocolGuid);

  ReportLoadedDrivers ();
  ReportPciFirmwareFile ();
  ReportDepex ();
  ReportHostPort ();

  Print (L"=== PHOTO THIS SCREEN ===\r\n");
  Print (L"'-' = no FV-path match; NOT definitive.\r\n");
  Print (L"No writes to disk, NVRAM or controllers.\r\n\r\n");
  return EFI_SUCCESS;
}
