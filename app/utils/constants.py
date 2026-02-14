# app/utils/constants.py
UNAUTHORIZED_ERROR = 401
NOT_FOUND_ERROR = 404
SUCCESS = 200
BAD_REQUEST_ERROR = 400
INTERNAL_SERVER_ERROR = 500

EXPLICIT_COMMANDS = {
    "/hs-contacts": ("contact", "Searching contacts"),
    "/hs-leads": ("lead", "Searching leads"),
    "/hs-deals": ("deal", "Searching deals"),
}
