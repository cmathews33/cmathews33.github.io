# DIY Craftsmanship Assistant - Session Context

## Project Overview
This is an Angular web application designed to assist users with DIY craftsmanship by generating design ideas based on space descriptions and dimensions.

## Current State
- **Framework**: Angular 21 with standalone components
- **State Management**: Angular Signals for reactive data handling
- **Forms**: Template-driven forms using FormsModule and [(ngModel)]
- **Styling**: Basic CSS with responsive design

## Key Features Implemented
1. **Photo Upload Input (Primary)**:
   - File input with preview display
   - Large, prominent upload area with dashed border and emoji icon
   - Image preview with clear button
   - Demo-only feature (does not actually process images)

2. **Optional Details Input (Secondary)**:
   - Textarea for space description (optional, reduced size)
   - Number inputs for dimensions: Length, Width, Height (in feet)

3. **Idea Generation**:
   - Uses room description and dimensions to create placeholder AI prompt messages
   - Detects room type from description keywords for context
   - Outputs generic AI generation guidance instead of hardcoded feature lists
   - Supports expanding individual ideas to reveal tools and materials

4. **UI Components**:
   - Centered container layout
   - Photo upload section with prominent styling
   - Optional details collapsible section
   - Generate button
   - Idea list with expandable materials dropdowns (per-idea)
   - Materials dropdown appears under each selected idea

## File Structure
```
src/app/
├── app.ts          # Main component with signals and generateIdeas() logic
├── app.html        # Template with form and ideas display
├── app.config.ts   # Router and providers setup
├── app.routes.ts   # Empty routes (single-page app)
└── app.css         # Global styles (currently empty)

src/
├── index.html      # Updated title: "DIY Craftsmanship Assistant"
└── main.ts         # Bootstrap file

Other:
├── AGENTS.md       # Development best practices and guidelines
├── README.md       # Project description and setup instructions
└── package.json    # Dependencies and scripts
```

## Code Patterns Used
- **Signals**: `imageFile`, `imagePreview`, `description`, `length`, `width`, `height`, `ideas`, `expandedIdeaIndex` as signal<File|null>, signal<string>, signal<number|string|string[]>, signal<number|null>
- **Event Handling**: `(change)="onImageSelected($event)"` for file input, `(click)="generateIdeas()"` on button, `(click)="toggleIdeaMaterials(i)"` for dropdown toggle
- **Conditional Rendering**: `@if`, `@else` for photo preview display; `*ngIf` for ideas section
- **Looping**: `*ngFor="let idea of ideas()"` for idea list
- **Two-way Binding**: `[(ngModel)]` for form inputs (description, dimensions)

## Generation Logic
The `generateIdeas()` method:
1. Reads the description and dimensions from signals
2. Detects a simple room type from keywords
3. Computes an area label for small, medium-sized, or large spaces
4. Sets a generic placeholder list asking for AI-generated ideas
5. Builds a connected placeholder tools and materials list for the selected idea

## Room Types Supported
- **Kitchen**: detected for placeholder labeling only
- **Living Room**: detected for placeholder labeling only
- **Bedroom**: detected for placeholder labeling only
- **Bathroom**: detected for placeholder labeling only
- **Generic**: fallback for undetermined descriptions

## Future Enhancement Opportunities
1. **Photo Analysis (AI Integration)**: Replace demo photo upload with actual image processing API to analyze space photos
2. **AI Integration**: Replace hardcoded logic with API calls for dynamic ideas based on photo or description
3. **More Room Types**: Add support for garage, office, patio, etc.
4. **Advanced Dimensions**: Support multiple units (meters, inches), irregular shapes
5. **Visual Output**: Add image suggestions or 3D previews based on uploaded photo
6. **User Preferences**: Save favorite ideas, customization options
7. **Material Suggestions**: Include DIY material lists and tools needed
8. **Accessibility**: Ensure full WCAG AAA compliance (currently at AA)
9. **Design Tone**: Maintain natural palette styling for production-ready appearance

## Development Notes
- Replaced hardcoded room suggestion lists with placeholder AI generation messaging.
- Added a new placeholder section for tools and materials needed to complete the job.
- Implemented idea selection so choosing a generated idea reveals connected materials guidance.
- Updated landing copy to make the tools/materials connection more prominent.
- Updated styles and layout to be fully responsive and avoid fixed positioning.
- Updated container sizing so the form and text area remain aligned on smaller screens.
- Updated styles to natural tones (light greens, tans, soft browns) for a production-ready appearance.
- Confirm current app component uses `src/app/app-styles.css` as the active stylesheet.
- Follows AGENTS.md best practices: standalone components, signals, no NgModules
- No external dependencies beyond Angular core
- Ready for `ng serve` to run locally
- No build errors detected in current implementation

## Recent Fixes (May 12, 2026)
- **app.html Syntax Errors**: Fixed corrupted HTML structure and CSS
  - Corrected misplaced `<ul>` element - moved inside `.ideas` div with proper `*ngIf` condition
  - Added missing `<h2>Design Ideas:</h2>` header for ideas section
  - Removed duplicate and malformed CSS rules
  - Ensured proper HTML nesting and CSS syntax

## Latest Updates (May 12, 2026 - Current Session)
- **Dimension Bubbles Spacing**: Increased gap from 1rem to 1.25rem to improve spacing and prevent overlap
- **Materials Refactored as Dropdowns**: 
  - Removed global `materials` signal from app.ts
  - Replaced `selectedIdeaIndex` with `expandedIdeaIndex` signal to track which idea's materials are expanded
  - Each idea now has its own collapsible materials section
  - Added `toggleIdeaMaterials(index)` method to toggle dropdown expansion
  - Added `getIdeaMaterials(index)` method to retrieve materials for a specific idea
- **Placeholder Content**: Updated idea format to "AI generated idea 1/2/3" and materials to "Tools for idea 1/2/3"
- **UI Improvements**:
  - Added toggle button next to each idea with visual chevron icon (▼)
  - Materials dropdown appears under each idea when button is clicked
  - Responsive toggle button sizing for different screen sizes
  - Smooth transitions and hover states for better UX
  - ARIA attributes added for accessibility (`aria-expanded`, `aria-label`)
- **CSS Updates**:
  - Improved dimension input spacing with increased gap
  - New `.idea-item`, `.idea-header`, `.materials-toggle`, `.materials-dropdown`, `.materials-list` styles
  - Toggle icon rotates 180° when expanded for visual feedback
  - Materials list has subtle background and border styling
  - Responsive adjustments for mobile screens
- **Accessibility**: Implemented proper ARIA labels and focus states for dropdown toggle buttons
  - Restored responsive form layout with flexbox for dimensions inputs
- **Style and Layout Update**: Applied a polished UI design
  - Created `src/app/app-styles.css` with a refined card layout, gradient background, rounded controls, and modern idea cards
  - Updated `src/app/app.ts` to use `styleUrls: ['./app-styles.css']`
  - Kept `src/app/app.html` clean with form markup only and no inline styles
- **Dimension Bubbles Spacing Fix**: Increased gap to 2rem to prevent overlapping (final fix)
- **Photo Upload Feature (Demo Only)**:
  - Added prominent photo upload section as primary user input
  - New signals: `imageFile` (File | null), `imagePreview` (base64 string)
  - New methods: `onImageSelected(event)` uses FileReader for preview generation, `clearImage()` removes image
  - Large dashed border upload area with emoji icon (📸) and hover effects
  - Photo preview displays with clear button (✕) overlay
  - Description textarea and dimensions moved to "Optional Details" collapsible section
  - Reordered form priority: photo upload first, optional details second
  - Updated page copy to emphasize photo as primary input method
  - Textarea height reduced from 140px to 100px (secondary input)
  - New CSS classes: `.photo-upload-section`, `.photo-input-wrapper`, `.hidden-input`, `.photo-upload-label`, `.photo-upload-content`, `.photo-icon`, `.photo-text`, `.primary-text`, `.photo-preview`, `.preview-img`, `.clear-image-btn`, `.optional-section`, `.optional-title`
  - Note: Feature is UI/demo only and does not actually process image data for AI ideas

## Environment Notes
- **OS**: macOS
- **Workspace path**: `/Users/kendallellmer/Desktop/ConnorGithub/general/my-app`
- **Current active file**: `src/app/app.html`
- **Last known terminal state**: attempted `npm start` and `npx ng serve --open` from workspace root, with non-zero exit statuses; current working directory is `/Users/kendallellmer/Desktop/ConnorGithub/general/my-app`
- **Important issue**: `src/app/app.css` became corrupted during styling changes, so a new stylesheet file was created and linked instead
- **Current app styling**: `app-styles.css` is the authoritative component stylesheet for `App`
- **Angular conventions**: following standalone component usage and signal-based state
</content>
<parameter name="filePath">/Users/kendallellmer/Desktop/ConnorGithub/general/my-app/CONTEXT.md