// SPDX-License-Identifier: GPL-3.0-or-later
// Derived from a separately validated SteamKit2 + NexusMods.Sdk MultiHasher workflow.
// Reads the official cached Steam manifest, verifies newly indexed files against its SHA-1,
// and emits data using the archived Nexus game-hashes JSON schema.
using System.Text.Json;
using NexusMods.Sdk.Hashes;
using SteamKit2;

if (args.Length != 6)
{
    Console.Error.WriteLine("Usage: HashProbe <manifest-file> <game-root> <dataset-root> <app-id> <depot-id> <manifest-id>");
    return 2;
}

var manifestFile = args[0];
var gameRoot = Path.GetFullPath(args[1]);
var datasetRoot = Path.GetFullPath(args[2]);
if (!uint.TryParse(args[3], out var appId) || !uint.TryParse(args[4], out var depotId) ||
    !ulong.TryParse(args[5], out var manifestId))
    throw new ArgumentException("Invalid numeric app/depot/manifest identifier");

if (!Directory.Exists(gameRoot) || !Directory.Exists(datasetRoot))
    throw new DirectoryNotFoundException("Game or dataset directory missing");

var manifest = DepotManifest.LoadFromFile(manifestFile)
    ?? throw new InvalidDataException("Unable to read Steam manifest");
if (manifest.DepotID != depotId || manifest.ManifestGID != manifestId)
    throw new InvalidDataException("Cached manifest does not match installed Steam depot manifest");
if (manifest.FilenamesEncrypted)
    throw new InvalidDataException("Encrypted Steam filenames: cannot verify official paths");

var appFile = Path.Combine(datasetRoot, "json", "stores", "steam", "apps", $"{appId}.json");
using (var appDoc = JsonDocument.Parse(File.ReadAllText(appFile)))
{
    var app = appDoc.RootElement;
    if (app.GetProperty("AppId").GetUInt32() != appId ||
        !app.GetProperty("Depots").EnumerateArray().Any(d => d.GetProperty("DepotId").GetUInt32() == depotId))
        throw new InvalidDataException("Archived Nexus hash dataset does not contain this Steam app/depot");
}

var index = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
var hashesRoot = Path.Combine(datasetRoot, "json", "hashes");
foreach (var recordFile in Directory.EnumerateFiles(hashesRoot, "*.json", SearchOption.AllDirectories))
{
    using var doc = JsonDocument.Parse(File.ReadAllText(recordFile));
    var sha = doc.RootElement.GetProperty("Sha1").GetString();
    if (!string.IsNullOrWhiteSpace(sha)) index.Add(sha);
}
Console.WriteLine($"Existing reference SHA-1 records: {index.Count}");

static string DbHex64(string value)
{
    var hex = value.StartsWith("0x", StringComparison.OrdinalIgnoreCase) ? value[2..] : value;
    var number = Convert.ToUInt64(hex, 16);
    return Convert.ToHexString(BitConverter.GetBytes(number));
}

var entries = (manifest.Files ?? throw new InvalidDataException("Steam manifest has no file list"))
    .Where(f => f.Chunks.Count > 0).ToArray();
if (entries.Length == 0) throw new InvalidDataException("Steam manifest contains no regular files");
var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
foreach (var f in entries)
{
    var rel = f.FileName.Replace('\\', '/');
    if (Path.IsPathRooted(rel) || rel.Split('/').Any(p => p == ".." || p == ""))
        throw new InvalidDataException($"Unexpected or unsafe path in Steam manifest: {rel}");
    if (!paths.Add(rel)) throw new InvalidDataException($"Duplicate Steam file path: {rel}");
}

int verifiedNew = 0, alreadyKnown = 0, skippedMissing = 0;
long newBytes = 0;
foreach (var file in entries)
{
    var rel = file.FileName.Replace('\\', '/');
    var expectedSha = Convert.ToHexString(file.FileHash);
    if (index.Contains(expectedSha)) { alreadyKnown++; continue; }

    var fullPath = Path.GetFullPath(Path.Combine(gameRoot, rel));
    if (!fullPath.StartsWith(gameRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar,
            StringComparison.Ordinal))
        throw new InvalidDataException($"Path escapes game root: {rel}");
    if (!File.Exists(fullPath))
    {
        skippedMissing++;
        throw new FileNotFoundException($"Steam manifest file missing; cannot mark as official: {rel}");
    }
    var physicalSize = new FileInfo(fullPath).Length;
    if (physicalSize != (long)file.TotalSize)
        throw new InvalidDataException($"Steam file size mismatch: {rel}, expected {file.TotalSize}, got {physicalSize}");

    Console.WriteLine($"Verifying {rel} ({file.TotalSize:N0} bytes)");
    await using var stream = File.OpenRead(fullPath);
    var result = await MultiHasher.HashStream(stream);
    if (!string.Equals(result.Sha1.ToString(), expectedSha, StringComparison.OrdinalIgnoreCase))
        throw new InvalidDataException($"Steam SHA-1 MISMATCH: {rel}. Stop and verify game files in Steam first.");

    var record = new
    {
        XxHash3 = DbHex64(result.XxHash3.ToString()),
        XxHash64 = DbHex64(result.XxHash64.ToString()),
        MinimalHash = DbHex64(result.MinimalHash.ToString()),
        Sha1 = result.Sha1.ToString(),
        Md5 = result.Md5.ToString(),
        Crc32 = Convert.ToHexString(BitConverter.GetBytes(result.Crc32.Value)),
        Size = result.Size.Value,
    };
    var hexId = result.XxHash3.ToString();
    if (hexId.StartsWith("0x", StringComparison.OrdinalIgnoreCase)) hexId = hexId[2..];
    hexId = hexId.ToUpperInvariant();
    var folder = Path.Combine(hashesRoot, hexId[..2]);
    Directory.CreateDirectory(folder);
    var output = Path.Combine(folder, hexId + ".json");
    var json = JsonSerializer.Serialize(record, new JsonSerializerOptions { WriteIndented = true });
    if (File.Exists(output) && File.ReadAllText(output).Trim() != json.Trim())
        throw new InvalidDataException($"Conflicting xxHash3 record: {output}");
    File.WriteAllText(output, json);
    index.Add(expectedSha);
    verifiedNew++;
    newBytes += physicalSize;
}

foreach (var f in entries)
    if (!index.Contains(Convert.ToHexString(f.FileHash)))
        throw new InvalidDataException($"Hash database lacks file {f.FileName}");

var exportedManifest = new
{
    ManifestId = manifest.ManifestGID,
    Files = entries.Select(f => new
    {
        Path = f.FileName.Replace('\\', '/'),
        Size = f.TotalSize,
        Hash = Convert.ToHexString(f.FileHash),
        Chunks = f.Chunks.Select(c => new
        {
            ChunkId = Convert.ToHexString(c.ChunkID ?? throw new InvalidDataException("Chunk ID missing")),
            Checksum = Convert.ToHexString(BitConverter.GetBytes(c.Checksum)),
            Offset = c.Offset,
            CompressedSize = c.CompressedLength,
            UncompressedSize = c.UncompressedLength,
        }).ToArray(),
    }).ToArray(),
    DepotId = manifest.DepotID,
    CreationTime = DateTime.SpecifyKind(manifest.CreationTime, DateTimeKind.Utc),
    TotalCompressedSize = manifest.TotalCompressedSize,
    TotalUncompressedSize = manifest.TotalUncompressedSize,
};
var manifestOutput = Path.Combine(datasetRoot, "json", "stores", "steam", "manifests", $"{manifestId}.json");
Directory.CreateDirectory(Path.GetDirectoryName(manifestOutput)!);
File.WriteAllText(manifestOutput, JsonSerializer.Serialize(exportedManifest,
    new JsonSerializerOptions { WriteIndented = true }));

Console.WriteLine($"Steam depot: {depotId}, manifest: {manifestId}, files: {entries.Length}");
Console.WriteLine($"Previously indexed: {alreadyKnown}; newly verified against Steam SHA-1: {verifiedNew}");
Console.WriteLine($"Newly read and verified bytes: {newBytes:N0}");
Console.WriteLine($"Manifest JSON: {manifestOutput}");
return skippedMissing == 0 ? 0 : 1;
