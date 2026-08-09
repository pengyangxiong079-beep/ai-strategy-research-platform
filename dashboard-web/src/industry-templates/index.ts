import { automotiveTemplate } from "./automotive";
import { generalTemplate, type IndustryTemplate } from "./general";

export function loadIndustryTemplate(templateId?: string | null): IndustryTemplate {
  return templateId === "automotive" ? automotiveTemplate : generalTemplate;
}
