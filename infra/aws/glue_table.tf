# ─────────────────────────────────────────────────────────────────────────────
# Glue Table for Athena — scores stored in S3
# Place this file in infra/aws/ alongside your existing .tf files
# ─────────────────────────────────────────────────────────────────────────────

resource "aws_glue_catalog_table" "scores" {
  name          = "scores"
  database_name = aws_glue_catalog_database.sentiment.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification"                = "json"
    "projection.enabled"            = "true"
    "projection.ticker.type"        = "enum"
    "projection.ticker.values"      = "AAPL,MSFT,GOOGL,AMZN,NVDA,TSLA,META,JPM,XOM,JNJ"
    "projection.date.type"          = "date"
    "projection.date.format"        = "yyyy-MM-dd"
    "projection.date.range"         = "2026-01-01,NOW"
    "projection.date.interval"      = "1"
    "projection.date.interval.unit" = "DAYS"
    "storage.location.template"     = "s3://${aws_s3_bucket.raw_articles.id}/scores/ticker=$${ticker}/date=$${date}"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.raw_articles.id}/scores/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "article_id"
      type = "string"
    }
    columns {
      name = "headline"
      type = "string"
    }
    columns {
      name = "source"
      type = "string"
    }
    columns {
      name = "source_url"
      type = "string"
    }
    columns {
      name = "published_at"
      type = "string"
    }
    columns {
      name = "sentiment"
      type = "string"
    }
    columns {
      name = "confidence"
      type = "double"
    }
    columns {
      name = "prob_positive"
      type = "double"
    }
    columns {
      name = "prob_negative"
      type = "double"
    }
    columns {
      name = "prob_neutral"
      type = "double"
    }
    columns {
      name = "low_confidence"
      type = "boolean"
    }
    columns {
      name = "scored_at"
      type = "string"
    }
  }

  partition_keys {
    name = "ticker"
    type = "string"
  }
  partition_keys {
    name = "date"
    type = "string"
  }
}
