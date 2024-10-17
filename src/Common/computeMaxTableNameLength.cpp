#include <Common/computeMaxTableNameLength.h>
#include <Common/escapeForFileName.h>

namespace DB
{

size_t computeMaxTableNameLength(const String & database_name, ContextPtr context)
{
    namespace fs = std::filesystem;

    const String suffix = ".sql.detached";
    const String metadata_path = fs::path(context->getPath()) / "metadata";
    const String metadata_dropped_path = fs::path(context->getPath()) / "metadata_dropped";

    // Helper lambda to get the maximum name length
    auto get_max_name_length = [](const String & path) -> size_t {
        auto length = pathconf(path.c_str(), _PC_NAME_MAX);
        return (length == -1) ? NAME_MAX : static_cast<size_t>(length);
    };

    size_t max_create_length = get_max_name_length(metadata_path) - suffix.length();
    size_t max_dropped_length = get_max_name_length(metadata_dropped_path);

    size_t escaped_db_name_length = escapeForFileName(database_name).length();
    const size_t uuid_length = 36; // Standard UUID length
    const size_t extension_length = 6; // Length of ".sql" including three dots

    // Adjust for database name and UUID in dropped table filenames
    size_t max_to_drop = max_dropped_length - escaped_db_name_length - uuid_length - extension_length;

    // Return the minimum of the two calculated lengths
    return std::min(max_create_length, max_to_drop);
}
}
