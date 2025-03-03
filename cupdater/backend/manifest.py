MANIFEST_SCHEMA={
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Manifest",
  "description": "Update manifest",
  "type": "object",
  "required": [
    "brand",
    "self",
    "branches",
    "layers"
  ],
  "properties": {
    "brand": {
      "description": "Branding information.",
      "type": "object",
      "required": ["name"],
      "properties": {
        "name": {
          "description": "Name of the application that will be used for in-app branding",
          "type": "string"
        }
      }
    },
    "self": {
      "description": "Self-update information.",
      "type": "object",
      "required": ["linux", "windows"],
      "properties": {
        "linux": {
          "$ref": "#/definitions/SelfUpdaterInfo"
        },
        "windows": {
          "$ref": "#/definitions/SelfUpdaterInfo"
        }
      }
    },
    "branches": {
      "description": "The list of branches that can be chosen by the user.",
      "type": "object",
      "required": ["public"],
      "propertyNames": {
        "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"
  	  },
      "additionalProperties": {
        "$ref": "#/definitions/BranchConfig"
      }
    },
    "layers": {
      "description": "The list of content layers",
      "type": "object",
      "propertyNames": {
        "pattern": "^[A-Za-z_-][A-Za-z0-9_-]*$"
  	  },
      "additionalProperties": {
        "$ref": "#/definitions/LayerConfig"
      }
    }
  },
  "definitions": {
    "BranchConfig": {
      "description": "A branch object that contains layers.",
      "type": "object",
      "required": [
        "layers"
      ],
      "properties": {
        "description": {
          "description": "Description for the branch",
          "type": "string"
        },
        "layers": {
          "description": "Downloadable layers of the branch",
          "type": "array",
          "items": {
            "description": "ID of the layer defined in #/layers/",
            "type": "string"
          }
        }
      }
    },
    "LayerConfig": {
      "description": "A layer is a subset of all files required to be downloaded.",
      "type": "object",
      "required": [
        "updated",
        "url"
      ],
      "properties": {
        "updated": {
          "description": "Unix timestamp of last update of the layer.",
          "type": "integer"
        },
        "url": {
          "description": "The link(s) to layer content",
          "type": "array",
          "items": {
            "type": "string"
          }
        }
      }
    },
    "SelfUpdaterInfo": {
      "description": "Self-updater info for this platform",
      "type": "object",
      "required": ["sha256", "url"],
      "properties": {
        "url": {
          "description": "URL to the new updater version",
          "type": "string"
        },
       	"sha256": {
          "description": "Hash of the new updater for update detection and verification purposes",
          "type": "string",
          "pattern": "[a-z0-9]{64}"
        }
      }
    }
  }
}