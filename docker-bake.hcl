group "default" {
    targets = ["protoncalendar-ro-api"]
}

variable "IMAGE" {
    default = "code.xcalts.co/christos/protoncalendar-ro-api"
}

variable "VERSION_TAG" { 
    default = "0.1.0"
}

target "protoncalendar-ro-api" {
    context    = "."
    dockerfile = "Dockerfile"
    tags       = ["${IMAGE}:${VERSION_TAG}"]
}

cache-to = "type=inline"
cache-from = "type=registry,ref=${IMAGE}:cache"
