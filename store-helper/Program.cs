using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Windows.ApplicationModel.Store.Preview.InstallControl;
using Windows.Management.Deployment;
using Windows.Services.Store;

namespace Javbed.StoreHelper;

static class Products
{
    public const string Legends = "9N98Z825TNFW";
    public const string Dungeons = "9P8MK4NC0LJB";
    public const string Dungeons2 = "9P5786PJB9RP";

    public static string IdFor(string key) => key.ToLowerInvariant() switch
    {
        "legends" => Legends,
        "dungeons" => Dungeons,
        "dungeons2" => Dungeons2,
        _ => throw new ArgumentException("Unknown product.")
    };
}

sealed record ProductInfo(string Title, string ProductId, string PackageFamilyName);

static class StoreApi
{
    static readonly StoreContext Context = StoreContext.GetDefault();
    static readonly PackageManager Packages = new();
    static readonly AppInstallManager Installs = new();
    static readonly string[] Kinds = ["Application","Game"];

    public static async Task<ProductInfo> Get(string productId)
    {

        var result = await Context.GetStoreProductsAsync(Kinds, [productId]);
        if (result.ExtendedError is { }) throw result.ExtendedError;
        var product = result.Products.Values.FirstOrDefault() ?? throw new InvalidOperationException("Store product not found.");
        using var doc = JsonDocument.Parse(product.ExtendedJsonData);
        var pfm = doc.RootElement.GetProperty("Properties").GetProperty("PackageFamilyName").GetString()
            ?? throw new InvalidOperationException("Package family name unavailable.");
        return new(product.Title, product.StoreId, pfm);
    }

    public static bool IsInstalled(ProductInfo info)
        => Packages.FindPackagesForUser(string.Empty, info.PackageFamilyName).Any();

    public static string? AppUserModelId(ProductInfo info)
    {
        var package = Packages.FindPackagesForUser(string.Empty, info.PackageFamilyName).FirstOrDefault();
        if (package is null) return null;
        try
        {
            var entries = package.GetAppListEntriesAsync().AsTask().GetAwaiter().GetResult();
            var entry = entries.FirstOrDefault();
            return entry?.AppUserModelId;
        }
        catch { return null; }
    }

    public static async Task Install(ProductInfo info)
    {
        AppInstallItem? item = Installs.AppInstallItems.FirstOrDefault(x => x.ProductId.Equals(info.ProductId, StringComparison.OrdinalIgnoreCase));
        if (item is null && IsInstalled(info))
            item = await Installs.UpdateAppByPackageFamilyNameAsync(info.PackageFamilyName);

        if (item is null)
        {
            // Game Pass / subscription titles may need Gaming Services entitlement materialized first.
            try
            {
                var user = Installs.GetFreeUserEntitlementAsync(info.ProductId, "", "").AsTask();
                var device = Installs.GetFreeDeviceEntitlementAsync(info.ProductId, "", "").AsTask();
                await Task.WhenAll(user, device);
                Console.WriteLine($"ENTITLEMENT|user={user.Result.Status}|device={device.Result.Status}");
            }
            catch (Exception ex)
            {
                Console.WriteLine("ENTITLEMENT|" + ex.Message);
            }
            item = await Installs.StartAppInstallAsync(info.ProductId, "", false, false);
        }
        if (item is null) throw new InvalidOperationException("Could not create install request.");

        Installs.MoveToFrontOfDownloadQueue(item.ProductId, "");
        var tcs = new TaskCompletionSource<bool>();
        void Report()
        {
            var s = item.GetCurrentStatus();
            Console.WriteLine($"PROGRESS|{(int)s.PercentComplete}|{s.InstallState}");
            if (s.InstallState == AppInstallState.Completed) tcs.TrySetResult(true);
            else if (s.InstallState == AppInstallState.Canceled) tcs.TrySetCanceled();
            else if (s.InstallState == AppInstallState.Error) tcs.TrySetException(s.ErrorCode);
        }
        item.StatusChanged += (_,__) => Report();
        item.Completed += (_,__) => Report();
        Report();
        await tcs.Task;
    }
}

class Program
{
    static async Task<int> Main(string[] args)
    {
        try
        {
            if (args.Length < 2) throw new ArgumentException("usage: javbed-store <status|install> <dungeons|dungeons2|legends>");
            var info = await StoreApi.Get(Products.IdFor(args[1]));
            switch (args[0].ToLowerInvariant())
            {
                case "status":
                    if (StoreApi.IsInstalled(info)) { Console.WriteLine("INSTALLED"); Console.WriteLine("APPID|" + (StoreApi.AppUserModelId(info) ?? "")); } else Console.WriteLine("NOT_INSTALLED");
                    return 0;
                case "install":
                    await StoreApi.Install(info);
                    Console.WriteLine("DONE");
                    return 0;
                default:
                    throw new ArgumentException("Unknown command.");
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 1;
        }
    }
}
