"""统一退出码与异常。

退出码是宿主判断结果的唯一依据，错误信息只写标准错误，且不得包含
记忆正文或命中的凭据原值。
"""

EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_NOT_FOUND = 3
EXIT_INTERNAL = 4


class MemError(Exception):
    exit_code = EXIT_INTERNAL

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ValidationError(MemError):
    exit_code = EXIT_VALIDATION


class FrontmatterError(ValidationError):
    pass


class NotFoundError(MemError):
    exit_code = EXIT_NOT_FOUND


class InternalError(MemError):
    exit_code = EXIT_INTERNAL
