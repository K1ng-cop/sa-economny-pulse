{#
  By default dbt builds "staging" models into a schema called "<target schema>_staging".
  This override uses the schema name exactly as configured, so models land in
  staging / intermediate / marts - the schemas init.sql created.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
