/** @file
  Read-only nabu USB firmware diagnostics.
  No ConnectController(), writes, NVRAM access, or PCI register access.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Library/UefiLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/BaseLib.h>
#include <Library/DevicePathLib.h>
#include <Protocol/DevicePath.h>
#include <Protocol/Usb2HostController.h>
#include <Protocol/UsbHostController.h>
#include <Protocol/UsbFunctionIo.h>
#include <Protocol/UsbIo.h>
#include <Protocol/PciIo.h>
#include <Protocol/PciRootBridgeIo.h>
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

  Print (L"\r\n=== NABU USB DIAG 02: READ ONLY ===\r\n");
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
  ReportHostPort ();

  Print (L"=== PHOTO THIS SCREEN ===\r\n");
  Print (L"'-' = no FV-path match; NOT definitive.\r\n");
  Print (L"No writes to disk, NVRAM or controllers.\r\n\r\n");
  return EFI_SUCCESS;
}
