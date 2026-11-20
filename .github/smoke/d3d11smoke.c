/*
 * D3D11 device and swap chain check for the Wine runtime smoke workflow.
 * Prints each HRESULT. Exits 0 only when every frame presents.
 */
#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <dxgi1_4.h>
#include <stdio.h>

#define WIDTH 640
#define HEIGHT 480
#define FRAMES 10

static const D3D_FEATURE_LEVEL feature_levels[] = {
    D3D_FEATURE_LEVEL_11_1,
    D3D_FEATURE_LEVEL_11_0,
};

static HRESULT create_device(HWND hwnd, DXGI_SWAP_EFFECT effect, const char *label,
                             ID3D11Device **device, ID3D11DeviceContext **context,
                             IDXGISwapChain **swap_chain, D3D_FEATURE_LEVEL *level)
{
    DXGI_SWAP_CHAIN_DESC desc = {0};
    HRESULT hr;

    desc.BufferCount = 2;
    desc.BufferDesc.Width = WIDTH;
    desc.BufferDesc.Height = HEIGHT;
    desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.OutputWindow = hwnd;
    desc.SampleDesc.Count = 1;
    desc.Windowed = TRUE;
    desc.SwapEffect = effect;

    hr = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0,
                                       feature_levels, ARRAYSIZE(feature_levels),
                                       D3D11_SDK_VERSION, &desc, swap_chain, device,
                                       level, context);
    printf("D3D11CreateDeviceAndSwapChain swap_effect=%s hr=0x%08lx\n", label, (unsigned long)hr);
    return hr;
}

static HRESULT query_adapter(ID3D11Device *device, char *name, size_t name_size)
{
    IDXGIDevice *dxgi_device = NULL;
    IDXGIAdapter *adapter = NULL;
    DXGI_ADAPTER_DESC desc;
    HRESULT hr;

    hr = ID3D11Device_QueryInterface(device, &IID_IDXGIDevice, (void **)&dxgi_device);
    printf("QueryInterface(IDXGIDevice) hr=0x%08lx\n", (unsigned long)hr);
    if (SUCCEEDED(hr)) {
        hr = IDXGIDevice_GetAdapter(dxgi_device, &adapter);
        printf("GetAdapter hr=0x%08lx\n", (unsigned long)hr);
    }
    if (SUCCEEDED(hr)) {
        hr = IDXGIAdapter_GetDesc(adapter, &desc);
        printf("GetDesc hr=0x%08lx\n", (unsigned long)hr);
    }
    if (SUCCEEDED(hr)) {
        WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, name, (int)name_size, NULL, NULL);
        printf("adapter description=\"%s\" vendor=0x%04x device=0x%04x dedicated_video_memory=%llu\n",
               name, desc.VendorId, desc.DeviceId, (unsigned long long)desc.DedicatedVideoMemory);
    }
    if (adapter) {
        IDXGIAdapter_Release(adapter);
    }
    if (dxgi_device) {
        IDXGIDevice_Release(dxgi_device);
    }
    return hr;
}

static HRESULT render_frames(ID3D11Device *device, ID3D11DeviceContext *context,
                             IDXGISwapChain *swap_chain)
{
    static const FLOAT clear_color[4] = {0.1f, 0.2f, 0.4f, 1.0f};
    HRESULT hr = S_OK;
    int frame;

    for (frame = 0; frame < FRAMES && SUCCEEDED(hr); frame++) {
        ID3D11Texture2D *back_buffer = NULL;
        ID3D11RenderTargetView *rtv = NULL;
        IDXGISwapChain3 *swap_chain3 = NULL;
        UINT index = 0;

        if (SUCCEEDED(IDXGISwapChain_QueryInterface(swap_chain, &IID_IDXGISwapChain3,
                                                    (void **)&swap_chain3))) {
            index = IDXGISwapChain3_GetCurrentBackBufferIndex(swap_chain3);
            IDXGISwapChain3_Release(swap_chain3);
        }
        hr = IDXGISwapChain_GetBuffer(swap_chain, index, &IID_ID3D11Texture2D,
                                      (void **)&back_buffer);
        if (SUCCEEDED(hr)) {
            hr = ID3D11Device_CreateRenderTargetView(device, (ID3D11Resource *)back_buffer,
                                                     NULL, &rtv);
        }
        if (SUCCEEDED(hr)) {
            ID3D11DeviceContext_OMSetRenderTargets(context, 1, &rtv, NULL);
            ID3D11DeviceContext_ClearRenderTargetView(context, rtv, clear_color);
            hr = IDXGISwapChain_Present(swap_chain, 0, 0);
        }
        printf("frame=%d back_buffer=%u hr=0x%08lx\n", frame, index, (unsigned long)hr);
        if (rtv) {
            ID3D11RenderTargetView_Release(rtv);
        }
        if (back_buffer) {
            ID3D11Texture2D_Release(back_buffer);
        }
    }
    return hr;
}

int main(void)
{
    WNDCLASSA wc = {0};
    HWND hwnd = NULL;
    ID3D11Device *device = NULL;
    ID3D11DeviceContext *context = NULL;
    IDXGISwapChain *swap_chain = NULL;
    D3D_FEATURE_LEVEL level = 0;
    char adapter[128] = "";
    const char *effect = "flip_discard";
    HRESULT hr;
    int rc = 1;

    setvbuf(stdout, NULL, _IONBF, 0);

    wc.lpfnWndProc = DefWindowProcA;
    wc.hInstance = GetModuleHandleA(NULL);
    wc.lpszClassName = "D3D11Smoke";
    if (!RegisterClassA(&wc)) {
        printf("RegisterClassA failed error=%lu\n", GetLastError());
        return 1;
    }
    hwnd = CreateWindowA("D3D11Smoke", "d3d11smoke", WS_OVERLAPPEDWINDOW,
                         CW_USEDEFAULT, CW_USEDEFAULT, WIDTH, HEIGHT,
                         NULL, NULL, wc.hInstance, NULL);
    if (!hwnd) {
        printf("CreateWindowA failed error=%lu\n", GetLastError());
        return 1;
    }
    ShowWindow(hwnd, SW_SHOW);

    hr = create_device(hwnd, DXGI_SWAP_EFFECT_FLIP_DISCARD, "flip_discard",
                       &device, &context, &swap_chain, &level);
    if (FAILED(hr)) {
        effect = "discard";
        hr = create_device(hwnd, DXGI_SWAP_EFFECT_DISCARD, "discard",
                           &device, &context, &swap_chain, &level);
    }
    if (FAILED(hr)) {
        printf("D3D11SMOKE fail stage=create_device hr=0x%08lx\n", (unsigned long)hr);
        goto cleanup;
    }
    printf("feature_level=0x%x\n", (unsigned int)level);

    hr = query_adapter(device, adapter, sizeof adapter);
    if (FAILED(hr)) {
        printf("D3D11SMOKE fail stage=adapter hr=0x%08lx\n", (unsigned long)hr);
        goto cleanup;
    }

    hr = render_frames(device, context, swap_chain);
    if (FAILED(hr)) {
        printf("D3D11SMOKE fail stage=present hr=0x%08lx\n", (unsigned long)hr);
        goto cleanup;
    }

    printf("D3D11SMOKE ok feature_level=0x%x swap_effect=%s adapter=%s\n",
           (unsigned int)level, effect, adapter);
    rc = 0;

cleanup:
    if (swap_chain) {
        IDXGISwapChain_Release(swap_chain);
    }
    if (context) {
        ID3D11DeviceContext_Release(context);
    }
    if (device) {
        ID3D11Device_Release(device);
    }
    if (hwnd) {
        DestroyWindow(hwnd);
    }
    return rc;
}
