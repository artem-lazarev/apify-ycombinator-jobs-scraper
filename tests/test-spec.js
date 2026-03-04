({ it, run, expectAsync, describe, expect }) => {
    const ACTOR_ID = "artemlazarevm/yc-jobs-scraper";
    const RUN_TIMEOUT_MS = 180000;

    const runActor = (input) => run({
        actorId: ACTOR_ID,
        input,
        options: { timeout: RUN_TIMEOUT_MS },
    });

    const assertDatasetShape = (items) => {
        if (items.length === 0) return;

        const sample = items[0];
        expect(sample).toHaveProperty("company");
        expect(sample).toHaveProperty("jobs");
        expect(sample).toHaveProperty("founders");

        expect(sample.company).toHaveProperty("name");
        expect(sample.company).toHaveProperty("slug");
        expect(sample.company).toHaveProperty("ycUrl");

        expect(Array.isArray(sample.jobs)).toBe(true);
        expect(Array.isArray(sample.founders)).toBe(true);

        if (sample.jobs.length > 0) {
            expect(sample.jobs[0]).toHaveProperty("jobId");
            expect(sample.jobs[0]).toHaveProperty("title");
            expect(sample.jobs[0]).toHaveProperty("jobUrl");
        }
    };

    describe("YC Jobs Scraper - Published Actor Reliability", () => {
        it("fast mode: should succeed and produce schema-compliant output", async () => {
            const result = await runActor({
                maxCompanies: 2,
                includeJobDetails: false,
                includeFounderDescriptions: true,
                rateLimitDelay: 0,
            });

            await expectAsync(result).toHaveStatus("SUCCEEDED");
            await expectAsync(result).withDataset((items) => {
                expect(items.length).toBeGreaterThan(0);
                assertDatasetShape(items);
            });
        });

        it("full detail mode: should succeed with job-page scraping enabled", async () => {
            const result = await runActor({
                maxCompanies: 1,
                includeJobDetails: true,
                includeFounderDescriptions: true,
                rateLimitDelay: 0.5,
            });

            await expectAsync(result).toHaveStatus("SUCCEEDED");
            await expectAsync(result).withDataset((items) => {
                expect(items.length).toBeGreaterThan(0);
                assertDatasetShape(items);
            });
        });

        it("narrow filters: should not fail even when result set is empty", async () => {
            const result = await runActor({
                maxCompanies: 5,
                filterByBatch: ["Z99"],
                filterByIndustry: ["nonexistent-industry-value"],
                filterByStage: ["nonexistent-stage-value"],
                includeJobDetails: false,
                rateLimitDelay: 0,
            });

            await expectAsync(result).toHaveStatus("SUCCEEDED");
            await expectAsync(result).withDataset((items) => {
                expect(Array.isArray(items)).toBe(true);
            });
        });

        it("top companies + location filters: should stay stable and emit valid rows", async () => {
            const result = await runActor({
                maxCompanies: 3,
                topCompaniesOnly: true,
                filterByLocation: ["Remote"],
                filterByIndustry: ["B2B", "Fintech"],
                includeJobDetails: false,
                includeFounderDescriptions: false,
                rateLimitDelay: 0,
            });

            await expectAsync(result).toHaveStatus("SUCCEEDED");
            await expectAsync(result).withDataset((items) => {
                assertDatasetShape(items);
            });
        });
    });
};
