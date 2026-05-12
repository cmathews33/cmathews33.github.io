import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, FormsModule, CommonModule],
  templateUrl: './app.html',
  styleUrls: ['./app-styles.css']
})
export class App {
  protected readonly title = signal('DIY Craftsmanship Assistant');

  imageFile = signal<File | null>(null);
  imagePreview = signal<string>('');
  description = signal('');
  length = signal(0);
  width = signal(0);
  height = signal(0);
  ideas = signal<string[]>([]);
  expandedIdeaIndex = signal<number | null>(null);
  private readonly materialOptions = signal<string[][]>([]);

  generateIdeas() {
    const desc = this.description().trim();
    const len = this.length();
    const wid = this.width();
    const hei = this.height();
    const area = len * wid;
    const areaLabel = area > 0 ? (area < 100 ? 'small' : area > 300 ? 'large' : 'medium-sized') : 'standard';

    const spaceType = /kitchen/i.test(desc)
      ? 'kitchen'
      : /living|living room|family room/i.test(desc)
      ? 'living room'
      : /bedroom/i.test(desc)
      ? 'bedroom'
      : /bathroom/i.test(desc)
      ? 'bathroom'
      : 'interior';

    const generatedIdeas = [
      `AI generated idea 1: Create a warm ${spaceType} layout with natural finishes and practical storage.`,
      `AI generated idea 2: Design an inviting ${spaceType} flow that balances comfort and function.`,
      `AI generated idea 3: Add layered lighting and thoughtful details to elevate the ${spaceType}.`
    ];

    this.ideas.set(generatedIdeas);
    this.materialOptions.set([
      [
        `Tools for idea 1:`,
        'Basic carpentry tools, wood finish samples, cabinet pulls, and shelving hardware.',
        'Soft textiles, warm paint tones, and natural material accents.'
      ],
      [
        `Tools for idea 2:`,
        'Measuring tools, layout templates, flexible furniture, and storage baskets.',
        'Neutral paint, layered rugs, and ambient lighting fixtures.'
      ],
      [
        `Tools for idea 3:`,
        'LED strips, dimmable bulbs, task lamps, and installation tools.',
        'Accent finishes, decorative trim, and soft textiles for texture.'
      ]
    ]);

    this.expandedIdeaIndex.set(null);
  }

  onImageSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.imageFile.set(file);
      const reader = new FileReader();
      reader.onload = (e) => {
        this.imagePreview.set(e.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  }

  clearImage() {
    this.imageFile.set(null);
    this.imagePreview.set('');
  }

  toggleIdeaMaterials(index: number) {
    if (this.expandedIdeaIndex() === index) {
      this.expandedIdeaIndex.set(null);
    } else {
      this.expandedIdeaIndex.set(index);
    }
  }

  getIdeaMaterials(index: number): string[] {
    return this.materialOptions()[index] ?? [];
  }
}
