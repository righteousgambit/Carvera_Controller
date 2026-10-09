// One-request filesystem helper. No Python, GUI runtime, or machine connection.
// Keep this protocol aligned with artifact_fs_worker.py; native parity is tested.
#import <Foundation/Foundation.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <unicode/uchar.h>
#include <unicode/ustring.h>

static BOOL startupTraceEnabled;
static void startupStage(const char *message) {
    // Fixed tokens only: never include paths, payloads, errors or environment.
    if (startupTraceEnabled) (void)write(STDERR_FILENO, message, strlen(message));
}

static void fail(NSString *message) {
    @throw [NSException exceptionWithName:@"FilesystemRequest" reason:message userInfo:nil];
}

static BOOL boolean(id value) {
    return value && CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID();
}

static BOOL validString(id value, NSUInteger limit, BOOL empty) {
    if (![value isKindOfClass:NSString.class]) return NO;
    NSData *scalars = [value dataUsingEncoding:NSUTF32LittleEndianStringEncoding];
    return scalars && scalars.length / 4 <= limit && (empty || [value length] > 0)
        && [value rangeOfString:[NSString stringWithFormat:@"%C", (unichar)0]].location == NSNotFound;
}

static NSString *fold(NSString *value) {
    // ICU's default full case fold includes expansions such as sharp-s -> ss.
    NSUInteger length = value.length;
    unichar *input = calloc(length + 1, sizeof(unichar));
    if (!input) fail(@"Unable to allocate folder metadata");
    [value getCharacters:input range:NSMakeRange(0, length)];
    UErrorCode status = U_ZERO_ERROR;
    int32_t capacity = u_strFoldCase(NULL, 0, input, (int32_t)length, U_FOLD_CASE_DEFAULT, &status);
    status = U_ZERO_ERROR;
    unichar *output = calloc((size_t)capacity + 1, sizeof(unichar));
    if (!output) { free(input); fail(@"Unable to allocate folder metadata"); }
    int32_t count = u_strFoldCase(output, capacity + 1, input, (int32_t)length, U_FOLD_CASE_DEFAULT, &status);
    free(input);
    NSString *result = U_SUCCESS(status) ? [NSString stringWithCharacters:output length:count] : nil;
    free(output);
    if (!result) fail(@"Unable to compare folder names");
    return result;
}

static NSString *lexicalPath(NSString *path) {
    // pathlib removes empty and '.' components, but preserves '..' so symlink
    // traversal is resolved by the filesystem rather than rewritten lexically.
    NSMutableArray *parts = [NSMutableArray array];
    for (NSString *part in [path componentsSeparatedByString:@"/"])
        if (part.length && ![part isEqual:@"."]) [parts addObject:part];
    NSString *joined = [parts componentsJoinedByString:@"/"];
    if ([path hasPrefix:@"/"]) return [@"/" stringByAppendingString:joined];
    return joined.length ? joined : @".";
}

static NSString *expand(NSString *path) {
    path = lexicalPath(path);
    if (![path hasPrefix:@"~"]) return path;
    NSRange slash = [path rangeOfString:@"/"];
    NSString *user = [path substringWithRange:NSMakeRange(1, (slash.location == NSNotFound ? path.length : slash.location) - 1)];
    const char *environmentHome = getenv("HOME");
    NSString *home = user.length ? NSHomeDirectoryForUser(user)
        : (environmentHome ? [NSString stringWithUTF8String:environmentHome] : NSHomeDirectory());
    if (!home) fail(@"Could not determine home directory");
    // Preserve absolute homes and trim only trailing slashes, as expanduser does.
    while (home.length && [home hasSuffix:@"/"]) home = [home substringToIndex:home.length - 1];
    NSString *expanded = [home stringByAppendingString:slash.location == NSNotFound ? @"" : [path substringFromIndex:slash.location]];
    return expanded.length ? expanded : @"/";
}

static NSUInteger asciiLowerBound(NSString *value) {
    NSUInteger count = 0;
    for (NSUInteger index = 0; index < value.length; index++)
        count += [value characterAtIndex:index] > 127 ? 6 : 1;
    return count;
}

static NSDictionary *execute(id request) {
    if (![request isKindOfClass:NSDictionary.class]) fail(@"Invalid filesystem request");
    NSString *operation = request[@"operation"], *path = request[@"path"];
    if (!validString(path, 16384, NO)) fail(@"Filesystem request needs a valid path");
    BOOL check = [operation isEqual:@"check"];
    if (check) {
        if ([request count] != 3 || !boolean(request[@"save"])) fail(@"Invalid file-check request");
    } else {
        if (![operation isEqual:@"list"]) fail(@"Unsupported filesystem operation");
        NSSet *allowed = [NSSet setWithArray:@[@"operation", @"path", @"suffixes", @"create", @"fallback"]];
        for (id key in request) if (![allowed containsObject:key]) fail(@"Unsupported folder-list request fields");
        id suffixes = request[@"suffixes"], create = request[@"create"], fallback = request[@"fallback"];
        if (![suffixes isKindOfClass:NSArray.class] || [suffixes count] > 128
            || (create && !boolean(create))
            || (fallback && fallback != NSNull.null && !validString(fallback, 16384, NO)))
            fail(@"Invalid folder-list request");
        for (id suffix in suffixes) if (!validString(suffix, 256, YES)) fail(@"Invalid folder-list request");
    }
    NSString *candidate = expand(path);
    struct stat info;
    BOOL exists = stat(candidate.fileSystemRepresentation, &info) == 0;
    if (check) {
        if ([request[@"save"] boolValue] && exists) fail(@"That file already exists. Choose a new name to preserve it.");
        if (![request[@"save"] boolValue] && (!exists || !S_ISREG(info.st_mode))) fail(@"Choose an existing file.");
        return @{};
    }
    if ([request[@"create"] boolValue]) {
        NSError *error = nil;
        if (![NSFileManager.defaultManager createDirectoryAtPath:candidate withIntermediateDirectories:YES attributes:nil error:&error])
            fail(error.localizedDescription);
        exists = stat(candidate.fileSystemRepresentation, &info) == 0;
    }
    id filename = NSNull.null;
    if (exists && S_ISREG(info.st_mode)) {
        filename = candidate.lastPathComponent;
        candidate = candidate.stringByDeletingLastPathComponent;
        if (!candidate.length) candidate = @".";
        exists = stat(candidate.fileSystemRepresentation, &info) == 0;
    }
    if (!exists || !S_ISDIR(info.st_mode)) {
        id fallback = request[@"fallback"];
        if (!fallback || fallback == NSNull.null) fail(@"That folder is unavailable. Enter an existing folder or file path.");
        candidate = expand(fallback);
    }
    char *resolved = realpath(candidate.fileSystemRepresentation, NULL);
    if (!resolved) fail([NSString stringWithUTF8String:strerror(errno)]);
    candidate = [NSFileManager.defaultManager stringWithFileSystemRepresentation:resolved length:strlen(resolved)];
    free(resolved);
    NSMutableArray *suffixes = [NSMutableArray array];
    for (NSString *suffix in request[@"suffixes"]) [suffixes addObject:fold(suffix)];
    DIR *directory = opendir(candidate.fileSystemRepresentation);
    if (!directory) fail([NSString stringWithUTF8String:strerror(errno)]);
    NSMutableArray *entries = [NSMutableArray array];
    NSUInteger count = 0;
    NSUInteger stringBytes = 0;
    NSUInteger prefixBytes = asciiLowerBound(candidate) + ([candidate hasSuffix:@"/"] ? 0 : 1);
    @try {
        struct dirent *child;
        while (YES) {
            errno = 0;
            child = readdir(directory);
            if (!child) {
                if (errno) fail([NSString stringWithUTF8String:strerror(errno)]);
                break;
            }
            if (!strcmp(child->d_name, ".") || !strcmp(child->d_name, "..")) continue;
            if (count++ >= 20000) fail(@"Folder has more than 20,000 items; enter a narrower folder");
            if (child->d_name[0] == '.') continue;
            NSString *name = [[NSString alloc] initWithBytes:child->d_name length:strlen(child->d_name) encoding:NSUTF8StringEncoding];
            if (!name) fail(@"Folder contains an unsupported filename");
            NSString *childPath = [candidate stringByAppendingPathComponent:name];
            struct stat details;
            // Resolve within the already-open directory. Rewalking a deep
            // absolute path for every entry needlessly repeats filesystem work.
            if (fstatat(dirfd(directory), child->d_name, &details, 0)) continue;
            BOOL isDirectory = S_ISDIR(details.st_mode), matches = isDirectory;
            NSString *folded = fold(name);
            for (NSString *suffix in suffixes) if (!suffix.length || [folded hasSuffix:suffix]) { matches = YES; break; }
            if (!matches) continue;
            // Both name and path are serialized. Once these valid strings alone
            // exceed the byte budget, even ignoring JSON syntax and all other
            // fields, the final response cannot fit. Avoid encoding that known
            // oversized payload; unreadable/filtered entries never contribute.
            stringBytes += prefixBytes + 2 * asciiLowerBound(name);
            if (stringBytes > 4 * 1024 * 1024) fail(@"Folder metadata exceeds limit; enter a narrower folder");
            [entries addObject:@{@"name":name, @"path":childPath, @"is_dir":@(isDirectory),
                @"size":@(details.st_size), @"modified":@(details.st_mtimespec.tv_sec + details.st_mtimespec.tv_nsec / 1e9), @"folded":folded}];
        }
    } @finally { closedir(directory); }
    [entries sortWithOptions:NSSortStable usingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        if ([a[@"is_dir"] boolValue] != [b[@"is_dir"] boolValue]) return [a[@"is_dir"] boolValue] ? NSOrderedAscending : NSOrderedDescending;
        // UTF-32 code point order, matching Python rather than locale/UTF-16 order.
        NSData *left = [a[@"folded"] dataUsingEncoding:NSUTF32BigEndianStringEncoding];
        NSData *right = [b[@"folded"] dataUsingEncoding:NSUTF32BigEndianStringEncoding];
        int order = memcmp(left.bytes, right.bytes, MIN(left.length, right.length));
        if (order) return order < 0 ? NSOrderedAscending : NSOrderedDescending;
        return left.length == right.length ? NSOrderedSame : (left.length < right.length ? NSOrderedAscending : NSOrderedDescending);
    }];
    NSMutableArray *clean = [NSMutableArray array];
    for (NSDictionary *entry in entries) {
        NSMutableDictionary *item = [entry mutableCopy];
        [item removeObjectForKey:@"folded"];
        [clean addObject:item];
    }
    return @{@"path":candidate, @"filename":filename, @"entries":clean};
}

static NSData *encode(NSDictionary *value) {
    NSError *error = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:value options:NSJSONWritingWithoutEscapingSlashes error:&error];
    if (!json) fail(@"Unable to encode folder metadata");
    if (json.length > 4 * 1024 * 1024) fail(@"Folder metadata exceeds limit; enter a narrower folder");
    NSString *text = [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding];
    unichar *characters = calloc(text.length + 1, sizeof(unichar));
    unsigned char *ascii = malloc(4 * 1024 * 1024 + 8);
    if (!characters || !ascii) {
        free(characters); free(ascii);
        fail(@"Unable to allocate folder metadata");
    }
    [text getCharacters:characters range:NSMakeRange(0, text.length)];
    size_t count = 0;
    BOOL quoted = NO, escaped = NO;
    for (NSUInteger index = 0; index < text.length; index++) {
        unichar character = characters[index];
        if (character > 127) {
            snprintf((char *)ascii + count, 7, "\\u%04x", character);
            count += 6;
        } else {
            unsigned char byte = character;
            ascii[count++] = byte;
            if (!quoted && (byte == ',' || byte == ':')) ascii[count++] = ' ';
        }
        if (count > 4 * 1024 * 1024) {
            free(characters); free(ascii);
            fail(@"Folder metadata exceeds limit; enter a narrower folder");
        }
        if (!escaped && character == '"') quoted = !quoted;
        escaped = !escaped && character == '\\';
    }
    free(characters);
    return [NSData dataWithBytesNoCopy:ascii length:count freeWhenDone:YES];
}

int main(void) {
    const char *trace = getenv("CARVERA_ARTIFACT_STARTUP_TRACE");
    startupTraceEnabled = trace && strcmp(trace, "1") == 0;
    startupStage("CARVERA_STARTUP main_entered\n");
    @autoreleasepool {
        NSData *payload;
        @try {
            unsigned char bytes[65538];
            size_t length = 0;
            int byte;
            while (length < sizeof(bytes) && (byte = getchar()) != EOF) {
                bytes[length++] = byte;
                if (byte == '\n') break;
            }
            startupStage("CARVERA_STARTUP request_read\n");
            if (length && bytes[length - 1] == '\n') length--;
            if (length > 65536) fail(@"Filesystem request exceeds limit");
            NSError *error = nil;
            id request = [NSJSONSerialization JSONObjectWithData:[NSData dataWithBytes:bytes length:length] options:NSJSONReadingFragmentsAllowed error:&error];
            if (!request) fail(@"Invalid filesystem JSON request");
            startupStage("CARVERA_STARTUP request_parsed\n");
            NSDictionary *result = execute(request);
            startupStage("CARVERA_STARTUP request_executed\n");
            payload = encode(@{@"result":result, @"error":NSNull.null});
            if (payload.length > 4 * 1024 * 1024) fail(@"Folder metadata exceeds limit; enter a narrower folder");
            startupStage("CARVERA_STARTUP response_encoded\n");
        } @catch (NSException *error) {
            payload = encode(@{@"result":NSNull.null, @"error":error.reason ?: @"Filesystem request failed"});
        }
        if (fwrite(payload.bytes, 1, payload.length, stdout) != payload.length || fflush(stdout)) return 1;
        startupStage("CARVERA_STARTUP response_written\n");
    }
    return 0;
}
